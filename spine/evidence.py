"""
Reproducible evidence packs.

A number in a dashboard is not evidence. Evidence is a claim, the population that
supports it, the method that produced it, the code version that computed it, and a
hash that proves none of those changed afterwards.

This exists because the automation frontier is destined for a Predetermined Change
Control Plan, and a PCCP has to state in advance which modifications are covered,
the methodology used to validate them, and the acceptance criteria. Six months later
a reviewer asks how you arrived at a number, and "re-run the endpoint" is not an
answer - the warehouse has moved and the model has shipped twice.

The hash covers inputs and result but NOT the timestamp, so regenerating from the
same warehouse state yields an identical hash. That is what makes a pack
reproducible rather than merely archived, and tests/test_spine.py asserts it.

A pack also records the exact case IDs behind a claim. Their own 510(k) summary
describes a restricted validation library that "aims to prevent" cases being used
for both training and validation - a procedural control where a system control
belongs. Recording the population turns that promise into something checkable.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spine import metrics

import os

ROOT = Path(__file__).resolve().parent.parent
# Overridable for the same reason as ACTIONS_DB: signed packs are written state.
EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR", ROOT / "evidence"))

SCHEMA_VERSION = "1.0"


def _sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   default=str).encode("utf-8")).hexdigest()


def code_version() -> str:
    """Git SHA if we are in a repo, otherwise a hash of the metric definitions.

    A number without the code that produced it is not reproducible. The fallback
    matters: this project may be shipped as a directory rather than a clone, and an
    evidence pack that silently records 'unknown' is worse than one that records a
    content hash of the logic.
    """
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, timeout=5)
        if sha.returncode == 0 and sha.stdout.strip():
            dirty = subprocess.run(
                ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                text=True, timeout=5)
            suffix = "-dirty" if dirty.stdout.strip() else ""
            return f"git:{sha.stdout.strip()[:12]}{suffix}"
    except (OSError, subprocess.SubprocessError):
        pass
    source = (Path(__file__).parent / "metrics.py").read_bytes()
    return f"metrics-sha256:{hashlib.sha256(source).hexdigest()[:12]}"


def spine_fingerprint(con) -> dict:
    """Pins the warehouse state a claim was computed against."""
    counts = {}
    for table in ("fct_case_spine", "fct_hazard_match", "fct_complaint", "dim_site"):
        counts[table] = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    # Hash of the case grain itself, so an added or removed case changes the
    # fingerprint even when the row count coincidentally matches.
    grain = con.execute(
        "SELECT string_agg(CAST(case_id AS VARCHAR), ',' ORDER BY case_id) "
        "FROM fct_case_spine").fetchone()[0] or ""
    return {"row_counts": counts, "grain_sha256": hashlib.sha256(
        grain.encode()).hexdigest()}


def population(con, where: str, params: list | None = None) -> dict:
    """The exact case population supporting a claim.

    Stores a hash plus the count rather than the full ID list - the list can run to
    hundreds of thousands of entries, and the hash is what makes contamination
    checkable against a training manifest. The IDs remain recoverable by re-running
    `where`, which is itself recorded.
    """
    ids = [r[0] for r in con.execute(
        f"SELECT case_id FROM fct_case_spine WHERE {where} ORDER BY case_id",
        params or []).fetchall()]
    return {
        "n": len(ids),
        "case_id_sha256": hashlib.sha256(
            ",".join(map(str, ids)).encode()).hexdigest(),
        "selector": where,
        "selector_params": params or [],
    }


def build_frontier_pack(con, tolerance: float = 0.08,
                        limitations: list[str] | None = None) -> dict:
    """Evidence pack for the automation-frontier claim.

    The claim: a defined subset of case strata can be processed without human
    correction at a stated residual actionable-correction rate.
    """
    strata = metrics.frontier(con)
    at = metrics.frontier_at(strata, tolerance)
    eligible = set(at["strata"])

    pop = population(con, f"{metrics.ACCEPTED}")
    eligible_pop = (
        population(con,
                   f"{metrics.ACCEPTED} AND stratum IN "
                   f"({','.join('?' * len(eligible))})", sorted(eligible))
        if eligible else {"n": 0, "case_id_sha256": None,
                          "selector": "none", "selector_params": []})

    content = {
        "schema_version": SCHEMA_VERSION,
        "claim_type": "automation_frontier",
        "claim": (
            f"At a residual actionable-correction rate of {tolerance:.2%} or below, "
            f"{at['eligible_strata']} of {at['total_strata']} case strata qualify, "
            f"covering {at['volume_share']:.1%} of accepted volume "
            f"({at['cases']} cases), at a blended residual rate of "
            f"{at['residual_rate']:.2%}."),
        "result": at,
        "supporting_detail": [s.__dict__ for s in strata],
        "population": {"reference": pop, "eligible": eligible_pop},
        "policy": {
            "decision_threshold": "FFR 0.80",
            "tolerance": tolerance,
            "min_stratum_n": metrics.MIN_STRATUM_N,
        },
        "method": {
            "metric": "actionable_correction_rate",
            "definition": (
                "share of accepted cases where analyst correction moved an FFR "
                "value across the 0.80 decision threshold"),
            "counterfactual": (
                "ffr_pre is FFR recomputed on pre-correction geometry; it is not "
                "stored upstream and is produced by batch re-solve"),
            "stratification": "calcium band x motion band x stent presence",
        },
        "code_version": code_version(),
        "spine_fingerprint": spine_fingerprint(con),
        "limitations": limitations or [
            "Observational. Strata are not randomised to automated versus "
            "human-corrected handling.",
            "Residual rate is estimated from historical corrections; it does not "
            "establish that automated handling of eligible strata is non-inferior.",
            "Strata below the minimum size are suppressed and excluded from the "
            "volume share.",
            "Case mix is not adjusted within strata.",
        ],
    }
    return finalise(content)


def build_disparity_pack(con, limitations: list[str] | None = None) -> dict:
    """Evidence pack for the subgroup-disparity monitoring claim."""
    result = metrics.subgroup_disparity(con)
    content = {
        "schema_version": SCHEMA_VERSION,
        "claim_type": "subgroup_disparity",
        "claim": (
            f"Across {result['policy']['comparisons']} subgroup comparisons on "
            f"{len(result['findings'])} axes, {len(result['escalations'])} arm(s) "
            f"met all escalation criteria."),
        "result": {"escalations": result["escalations"],
                   "findings": result["findings"]},
        "population": population(con, metrics.ACCEPTED),
        "policy": result["policy"],
        "method": {
            "multiplicity": "Benjamini-Hochberg step-up, FDR controlled",
            "interval": "Wilson score, 95%",
            "escalation": ("conjunctive: FDR-significant AND disparity ratio >= "
                           f"{metrics.MIN_DISPARITY} AND arm n >= {metrics.MIN_ARM_N}"),
        },
        "code_version": code_version(),
        "spine_fingerprint": spine_fingerprint(con),
        "limitations": limitations or [
            "Clinical and operational subgroups only. The spine carries no "
            "demographics, so this is not demographic equity analysis.",
            "FDR q=0.10 means roughly one in ten flagged findings is expected to "
            "be a false lead.",
            "Subgroup axes are correlated; they are not independent experiments.",
        ],
    }
    return finalise(content)


def finalise(content: dict) -> dict:
    """Attach the manifest hash.

    The hash covers `content` only. `generated_at` sits outside it deliberately, so
    two runs against the same warehouse state produce the same hash - which is what
    makes reproducibility testable rather than asserted.
    """
    return {
        "content": content,
        "manifest_sha256": _sha256(content),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def verify(pack: dict) -> tuple[bool, str]:
    """Recompute the hash and compare. An edited pack fails."""
    if "content" not in pack or "manifest_sha256" not in pack:
        return False, "malformed pack: missing content or manifest_sha256"
    recomputed = _sha256(pack["content"])
    if recomputed != pack["manifest_sha256"]:
        return False, (f"hash mismatch - content was modified after signing "
                       f"(stored {pack['manifest_sha256'][:12]}, "
                       f"recomputed {recomputed[:12]})")
    return True, "verified"


def persist(pack: dict, directory: Path | None = None) -> Path:
    """Write content-addressed and never overwrite.

    Immutability is enforced by the filename: the same content lands on the same
    path, and different content cannot collide with it.
    """
    directory = directory or EVIDENCE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    claim = pack["content"]["claim_type"]
    path = directory / f"{claim}-{pack['manifest_sha256'][:16]}.json"
    if path.exists():
        return path
    path.write_text(json.dumps(pack, indent=2, default=str), encoding="utf-8")
    return path


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
