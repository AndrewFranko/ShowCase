"""
Source-system extractors.

In production each function below is a Dagster asset backed by a real connector:

    case_management   -> Aurora/Postgres read replica (CDC or nightly snapshot)
    analyst_events    -> S3 label store (the corrections already persisted for training)
    complaints        -> Smarteeva REST API (Salesforce-backed)
    risk_file         -> Ketryx API
    scanner_registry  -> DICOM header extraction at ingest

Here they read from a locally generated fixture so the whole pipeline runs with no
infrastructure. The *shape* of what each returns is the contract that matters; swapping
the body for a real connector does not change anything downstream.

PHI boundary: none of these return pixel data, DICOM UIDs, accession numbers, patient
identifiers, or raw mesh geometry. Case identity is a surrogate integer. Analyst identity
is not extracted at all.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "raw"


def _read(name: str) -> list[dict[str, Any]]:
    path = FIXTURE / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python -m spine.generate` first "
            "(or `make seed`) to build the local fixture."
        )
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def case_management() -> list[dict[str, Any]]:
    """One row per case as the case-management system knows it.

    Production: SELECT from the ops read replica. Columns are chosen to be the
    minimum needed downstream — this is deliberately not `SELECT *`.
    """
    return _read("cases")


def analyst_events() -> list[dict[str, Any]]:
    """Correction events, aggregated to case grain.

    Production: the label store. Note that the *pre-correction geometry* is the
    important artifact here — recomputing FFR on it is what produces `ffr_pre`.
    That solve is a batch job, not a telemetry feed.
    """
    return _read("analyst_events")


def complaints() -> list[dict[str, Any]]:
    """Complaint records joined to the case they concern."""
    return _read("complaints")


def risk_file() -> list[dict[str, Any]]:
    """Hazards from the risk management file, each carrying a machine-evaluable
    signature. In production this is pulled from Ketryx; the `signature` field is
    authored by Quality, reviewed, and version-controlled alongside the hazard."""
    return _read("hazards")


def scanner_registry() -> list[dict[str, Any]]:
    """Site and scanner dimension, including detector generation over time.

    Detector generation is time-varying: a site that swaps EID for photon-counting
    changes the meaning of its plaque measurements. Carrying it on the case row is
    the only way that shift becomes visible.
    """
    return _read("sites")


ALL_SOURCES = {
    "cases": case_management,
    "analyst_events": analyst_events,
    "complaints": complaints,
    "hazards": risk_file,
    "sites": scanner_registry,
}


def env(key: str, default: str) -> str:
    return os.environ.get(key, default)
