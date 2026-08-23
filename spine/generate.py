"""
Builds a local fixture in *source-system shape*.

This deliberately emits five separate raw tables that look like what each upstream
system would actually hand you — un-joined, with the derived columns absent. All the
interesting work (detector-at-scan-time, stratum assignment, delta-FFR, hazard
signature evaluation) happens in SQL in spine/models/, because that is where it
would happen in production.

Domain constants come from public disclosure and the CCTA literature:
  FFR decision threshold 0.80, grey zone 0.75-0.80
  median analyst processing 26 min; median turnaround 1.6 h
  real-world rejection 8-15%; motion artifact ~78% of rejections (ADVANCE)
  automation failure predicted by stents and Agatston >967
  photon-counting CT measures ~1/3 lower total plaque volume (Radiology 2025)
  SCCT/SCAI 2026 consensus requires nitroglycerin and heart-rate control

Three signals are planted so the lenses have something true to find; see PLANTED at
the bottom of this file.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "raw"

N_CASES = 12000
N_SITES = 140
DAYS = 182

SEGMENTS = ["LM", "pLAD", "mLAD", "dLAD", "D1", "pLCx", "dLCx", "OM1", "pRCA", "mRCA", "dRCA"]
SEG_W = {"LM": 1.00, "pLAD": 0.95, "mLAD": 0.70, "dLAD": 0.30, "D1": 0.35,
         "pLCx": 0.65, "dLCx": 0.25, "OM1": 0.35, "pRCA": 0.70, "mRCA": 0.50, "dRCA": 0.22}

SCANNERS = [
    ("Siemens", "SOMATOM Force", "EID", 0.93),
    ("Siemens", "NAEOTOM Alpha", "PCD", 0.97),
    ("GE", "Revolution Apex", "EID", 0.90),
    ("Canon", "Aquilion ONE", "EID", 0.91),
    ("Philips", "Spectral CT 7500", "EID", 0.88),
]

MODEL_VERSIONS = [("v4.0.2", 0), ("v4.1.0", 95), ("v4.1.3", 148)]

HAZARDS = [
    {"hazard_id": "H-014",
     "title": "Vessel lumen over-segmented in proximal segment leading to false negative FFR",
     "signature": "proximal_overwide",
     "controls": ["Analyst quality inspection", "Automated QC heuristics"]},
    {"hazard_id": "H-022",
     "title": "Analysis released on study failing image-quality criteria",
     "signature": "bad_quality_accepted",
     "controls": ["Ingest gate", "Analyst quality inspection"]},
    {"hazard_id": "H-031",
     "title": "Undetected stent in target vessel yields non-physiologic FFR",
     "signature": "stent_missed",
     "controls": ["Contraindication screen", "Analyst quality inspection"]},
    {"hazard_id": "H-047",
     "title": "Plaque volume misreported following scanner detector change",
     "signature": "detector_shift",
     "controls": ["Site qualification", "Scanner conformance monitoring"]},
]

REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West", "Great Lakes"]
STEMS = ["Northshore", "Baypoint", "Cedar Ridge", "Fairmount", "Highland Park", "Ironwood",
         "Lakeview", "Meridian", "Oakhurst", "Pinecrest", "Riverbend", "Stonegate", "Summit",
         "Westgate", "Willow Creek", "Ashford", "Brookhaven", "Clearwater", "Dunmore",
         "Eastvale", "Foxglove", "Granite Bay", "Harborview", "Inglewood"]
KINDS = ["Cardiovascular Institute", "Heart & Vascular", "Regional Medical Center",
         "Cardiology Associates", "Medical Center", "Imaging Partners"]


def model_version_at(day: int) -> str:
    cur = MODEL_VERSIONS[0][0]
    for v, d in MODEL_VERSIONS:
        if day >= d:
            cur = v
    return cur


def build(seed: int = 4152026) -> dict[str, list[dict]]:
    rng = random.Random(seed)

    # ---------------------------------------------------------------- sites
    sites, used = [], {}
    for i in range(N_SITES):
        make, model, det, quality = rng.choice(SCANNERS)
        name = f"{rng.choice(STEMS)} {rng.choice(KINDS)}"
        used[name] = used.get(name, 0) + 1
        if used[name] > 1:
            name = f"{name} #{used[name]}"
        sites.append({
            "site_id": i,
            "site_name": name,
            "region": rng.choice(REGIONS),
            "scanner_make": make,
            "scanner_model": model,
            "detector_default": det,
            "detector_switch_day": None,
            "is_office": int(rng.random() < 0.36),
            # latent, never exported: how well the site controls HR / gives nitro
            "_technique": min(0.99, max(0.28, rng.gauss(0.78, 0.14))),
            # latent: referral severity. Tertiary centres see older, heavier, more
            # calcified patients than a suburban clinic. Without this the network
            # has identical case mix everywhere, which makes case-mix adjustment a
            # no-op and hides whether the adjustment works at all.
            "_severity": min(2.2, max(0.45, rng.lognormvariate(0.0, 0.34))),
            "_weight": max(0.15, rng.gauss(1.0, 0.45)),
            "field_visit_days": [],
        })

    # PLANTED 1 - two sites migrate to photon-counting mid-window
    for sid, day in ((17, 104), (63, 121)):
        sites[sid]["detector_switch_day"] = day
        sites[sid]["scanner_make"] = "Siemens"
        sites[sid]["scanner_model"] = "NAEOTOM Alpha"

    # PLANTED 2 - field visits to the nine worst-technique sites
    for s in sorted(sites, key=lambda x: x["_technique"])[:9]:
        s["field_visit_days"].append(rng.randint(55, 92))

    def technique_at(site, day):
        t = site["_technique"]
        for v in site["field_visit_days"]:
            if day >= v:
                t = min(0.97, t + 0.20)
        return t

    def detector_at(site, day):
        if site["detector_switch_day"] is not None:
            return "PCD" if day >= site["detector_switch_day"] else "EID"
        return site["detector_default"]

    weights = [s["_weight"] for s in sites]

    # ---------------------------------------------------------------- cases
    cases, events = [], []
    for cid in range(N_CASES):
        day = rng.randint(0, DAYS - 1)
        site = rng.choices(sites, weights=weights, k=1)[0]
        tech = technique_at(site, day)
        det = detector_at(site, day)
        mv = model_version_at(day)
        scan_q = next(q for mk, md, _, q in SCANNERS
                      if mk == site["scanner_make"] and md == site["scanner_model"])

        # Case mix varies by site: referral severity scales calcium burden and BMI.
        # This is what makes case-mix adjustment meaningful - a tertiary centre
        # rejecting more studies than a suburban clinic may be doing nothing wrong.
        sev = site["_severity"]
        agatston = 148 * sev * math.exp(rng.gauss(0, 1.45))
        hr = rng.gauss(72 - tech * 16, 9.0)
        hr_var = abs(rng.gauss(0, 1)) * (2.2 if hr < 68 else 5.0)
        bmi = rng.gauss(29.2 + (sev - 1.0) * 3.4, 5.6)
        stent = rng.random() < 0.081
        nitro = rng.random() < (0.45 + tech * 0.5)

        motion = max(0.0, hr - 58) * 0.055 + hr_var * 0.16 + rng.gauss(0, 0.42)
        motion += max(0.0, bmi - 30) * 0.035 + (0.0 if nitro else 0.25)
        motion = max(0.0, min(3.0, motion))

        noise = max(0.0, rng.gauss(1.0, 0.33) + max(0.0, bmi - 28) * 0.055 - (scan_q - 0.90) * 2.0)

        conf = 0.94
        conf -= min(0.26, math.log1p(agatston / 240.0) * 0.135)
        conf -= motion * 0.105 + noise * 0.045
        conf -= 0.11 if stent else 0.0
        conf += 0.025 if det == "PCD" else 0.0
        # PLANTED 3 - v4.1.0 regressed on Canon reconstructions; v4.1.3 fixed it
        if mv == "v4.1.0" and site["scanner_make"] == "Canon":
            conf -= 0.105
        conf = max(0.18, min(0.995, conf + rng.gauss(0, 0.045)))

        p_rej = 0.010 + motion * 0.050 + (0.075 if stent else 0.0) + noise * 0.018
        p_rej += 0.05 if agatston > 967 else 0.0
        accepted = rng.random() >= min(0.55, p_rej)
        reason = None
        if not accepted:
            r = rng.random()
            reason = ("motion_artifact" if r < 0.78 else
                      "contrast_opacification" if r < 0.88 else
                      "misregistration" if r < 0.95 else "coverage_incomplete")

        difficulty = 1.0 - conf
        tpv = max(20.0, rng.gauss(760 + math.log1p(agatston) * 118, 260))
        if det == "PCD":
            tpv *= 0.66

        n_edits = max(0, int(rng.gauss(difficulty * 46, 6)))
        active = max(3.0, rng.gauss(9.5 + difficulty * 52, 5.5))
        idle = max(0.0, rng.gauss(active * 0.22, 2.4))

        n_seg = max(1, min(len(SEGMENTS), int(rng.gauss(1.6 + difficulty * 6.0, 1.4))))
        pool = [(s, SEG_W[s] ** (1.0 / max(0.12, difficulty * 2.2))) for s in SEGMENTS]
        touched = []
        for _ in range(n_seg):
            total = sum(w for _, w in pool)
            pick, acc_w = rng.uniform(0, total), 0.0
            for j, (s, w) in enumerate(pool):
                acc_w += w
                if pick <= acc_w:
                    touched.append(s)
                    pool.pop(j)
                    break
        prox_w = max(SEG_W[s] for s in touched)

        ffr_pre = min(0.99, max(0.42, rng.gauss(0.825, 0.095)))
        shift = abs(rng.gauss(0, 0.004 + (difficulty ** 1.7) * 0.30 * prox_w))
        ffr_post = max(0.35, min(0.99, ffr_pre + (-1 if rng.random() < 0.62 else 1) * shift))

        cases.append({
            "case_id": cid,
            "case_day": day,
            "site_id": site["site_id"],
            "model_version": mv,
            "agatston": round(agatston, 1),
            "heart_rate": round(hr, 1),
            "bmi": round(bmi, 1),
            "stent_present": int(stent),
            "nitro_given": int(nitro),
            "motion_score": round(motion, 2),
            "autoseg_confidence": round(conf, 4),
            "accepted": int(accepted),
            "reject_reason": reason,
            "total_plaque_volume_mm3": round(tpv, 1),
            "turnaround_min": round(active + idle + max(12.0, rng.gauss(46, 16)), 1),
        })

        if accepted:
            events.append({
                "case_id": cid,
                "edit_count": n_edits,
                "active_min": round(active, 1),
                "idle_min": round(idle, 1),
                "segments_touched": touched,
                "ffr_pre": round(ffr_pre, 4),
                "ffr_post": round(ffr_post, 4),
            })

    # ---------------------------------------------------------------- complaints
    by_id = {c["case_id"]: c for c in cases}
    ev_id = {e["case_id"]: e for e in events}
    complaints = []
    for e in events:
        c = by_id[e["case_id"]]
        prox = any(SEG_W[s] >= 0.65 for s in e["segments_touched"])
        d = e["ffr_post"] - e["ffr_pre"]
        h014 = prox and d > 0.045 and e["ffr_post"] > 0.80
        h031 = c["stent_present"] and prox and abs(d) > 0.04
        h022 = c["motion_score"] >= 1.6
        p = 0.0009 + (0.075 if h014 else 0) + (0.055 if h031 else 0) + (0.012 if h022 else 0)
        if rng.random() < p:
            ctype = ("false_negative" if h014 else
                     "contraindication_missed" if h031 else
                     "image_quality" if h022 else "result_discrepancy")
            complaints.append({
                "complaint_id": len(complaints),
                "case_id": c["case_id"],
                "complaint_day": min(DAYS - 1, c["case_day"] + int(abs(rng.gauss(34, 22))) + 4),
                "complaint_type": ctype,
                "mdr_reportable": int(ctype in ("false_negative", "contraindication_missed")
                                      and rng.random() < 0.55),
                "status": rng.choice(["closed", "closed", "closed", "under_investigation"]),
            })

    for s in sites:
        s.pop("_technique", None)
        s.pop("_weight", None)

    return {"sites": sites, "cases": cases, "analyst_events": events,
            "complaints": complaints, "hazards": HAZARDS}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tables = build()
    for name, rows in tables.items():
        (OUT / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")
        print(f"{name:16s} {len(rows):6d} rows -> {OUT / (name + '.json')}")


if __name__ == "__main__":
    main()


# PLANTED SIGNALS ------------------------------------------------------------
# 1. Sites 17 and 63 switch EID -> photon-counting on days 104 and 121. Their
#    total plaque volume drops ~34% with no change in case mix and no error raised.
# 2. Nine low-technique sites receive a field visit between days 55-92; rejection
#    falls afterwards, which closes the "did the visit work" loop.
# 3. Model v4.1.0 (days 95-147) regressed on Canon reconstructions only. v4.1.3
#    fixed it. Median analyst minutes barely move, so throughput dashboards miss it
#    entirely; actionable-correction rate and complaint volume both show it.
