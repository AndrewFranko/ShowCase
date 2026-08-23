"""
Generates a synthetic *case spine* for the Heartflow analysis pipeline.

The point of this file is not the data. It is the SHAPE: one immutable row per
case, joined to conformed dimensions (site, scanner, model version, stratum),
with downstream facts (complaints, MDRs, hazard matches) referencing the same
grain. Every lens in the portal is a projection over this one table.

Domain constants are taken from Heartflow's public disclosures and the CCTA
literature, not invented:
  - FFR decision threshold 0.80; grey zone 0.75-0.80
  - median analyst processing 26 min (S-1, Q4 2024); median TAT 1.6 h
  - real-world rejection 8-15%; motion artifact ~78% of rejections (ADVANCE)
  - automation failure predicted by stents (p=0.001) and Agatston >967 (p=0.039)
  - photon-counting CT measures ~1/3 less total plaque volume than EID
    (Radiology 2025) - EID-derived HU thresholds do not transfer
  - SCCT/SCAI 2026 consensus requires nitroglycerin + heart-rate control

Three signals are deliberately planted so the cross-reference lenses have
something true to find. They are listed at the bottom of this file.
"""
import json, math, random

random.seed(4152026)

N_CASES = 3600
DAYS = 182                      # two quarters

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

MODELS = [("v4.0.2", 0), ("v4.1.0", 95), ("v4.1.3", 148)]

HAZARDS = [
    ("H-014", "Vessel lumen over-segmented in proximal segment leading to false negative FFR",
     "proximal_overwide", ["Analyst quality inspection", "Automated QC heuristics"]),
    ("H-022", "Analysis released on study failing image-quality criteria",
     "bad_quality_accepted", ["Ingest gate", "Analyst quality inspection"]),
    ("H-031", "Undetected stent in target vessel yields non-physiologic FFR",
     "stent_missed", ["Contraindication screen", "Analyst quality inspection"]),
    ("H-047", "Plaque volume misreported following scanner detector change",
     "detector_shift", ["Site qualification", "Scanner conformance monitoring"]),
]

REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West", "Great Lakes"]
SITE_STEMS = ["Northshore", "Baypoint", "Cedar Ridge", "Fairmount", "Highland Park", "Ironwood",
              "Lakeview", "Meridian", "Oakhurst", "Pinecrest", "Riverbend", "Stonegate",
              "Summit", "Westgate", "Willow Creek", "Ashford", "Brookhaven", "Clearwater",
              "Dunmore", "Eastvale", "Foxglove", "Granite Bay", "Harborview", "Inglewood"]
SITE_KINDS = ["Cardiovascular Institute", "Heart & Vascular", "Regional Medical Center",
              "Cardiology Associates", "Medical Center", "Imaging Partners"]

# ---------------------------------------------------------------- sites
sites = []
for i in range(140):
    make, model, det, q = random.choice(SCANNERS)
    # latent acquisition-technique quality: how well the site controls heart rate,
    # gives nitro, and picks reconstruction parameters
    technique = min(0.99, max(0.28, random.gauss(0.78, 0.14)))
    office = random.random() < 0.36          # office/clinic vs hospital - pays less
    sites.append({
        "id": i,
        "name": f"{random.choice(SITE_STEMS)} {random.choice(SITE_KINDS)}",
        "region": random.choice(REGIONS),
        "make": make, "model": model,
        "detector": det,
        "detector_switch_day": None,
        "technique": technique,
        "office": office,
        "weight": max(0.15, random.gauss(1.0, 0.45)),
        "visits": [],
    })

# uniquify names
seen = {}
for s in sites:
    if s["name"] in seen:
        seen[s["name"]] += 1
        s["name"] = f'{s["name"]} #{seen[s["name"]]}'
    else:
        seen[s["name"]] = 1

# --- PLANTED SIGNAL 1: two sites swap EID -> photon-counting mid-period
for sid, day in ((17, 104), (63, 121)):
    sites[sid]["detector_switch_day"] = day
    sites[sid]["model"] = "NAEOTOM Alpha"
    sites[sid]["make"] = "Siemens"

# --- PLANTED SIGNAL 2: field-service visits to the worst-technique sites,
#     after which acquisition quality improves (so the loop can be measured)
worst = sorted(sites, key=lambda s: s["technique"])[:9]
for s in worst:
    d = random.randint(55, 92)
    s["visits"].append(d)


def technique_at(site, day):
    t = site["technique"]
    for v in site["visits"]:
        if day >= v:
            t = min(0.97, t + 0.20)          # a visit is worth ~20 points of technique
    return t


def detector_at(site, day):
    if site["detector_switch_day"] is not None:
        return "PCD" if day >= site["detector_switch_day"] else "EID"
    return site["detector"]


def model_at(day):
    cur = MODELS[0][0]
    for v, d in MODELS:
        if day >= d:
            cur = v
    return cur


site_weights = [s["weight"] for s in sites]

# ---------------------------------------------------------------- cases
cases = []
for i in range(N_CASES):
    day = random.randint(0, DAYS - 1)
    site = random.choices(sites, weights=site_weights, k=1)[0]
    tech = technique_at(site, day)
    det = detector_at(site, day)
    mv = model_at(day)

    scan_q = next((q for mk, md, dt, q in SCANNERS if mk == site["make"] and md == site["model"]), 0.90)

    calcium = 148 * math.exp(random.gauss(0, 1.45))
    hr = random.gauss(72 - tech * 16, 9.0)              # good technique = beta-blocked
    hr_var = abs(random.gauss(0, 1)) * (2.2 if hr < 68 else 5.0)
    bmi = random.gauss(29.2, 5.6)
    stent = random.random() < 0.081
    nitro = random.random() < (0.45 + tech * 0.5)

    motion = max(0.0, hr - 58) * 0.055 + hr_var * 0.16 + random.gauss(0, 0.42)
    motion += max(0.0, bmi - 30) * 0.035
    motion += 0.0 if nitro else 0.25
    motion = max(0.0, min(3.0, motion))

    noise = max(0.0, random.gauss(1.0, 0.33) + max(0.0, bmi - 28) * 0.055 - (scan_q - 0.90) * 2.0)

    conf = 0.94
    conf -= min(0.26, math.log1p(calcium / 240.0) * 0.135)
    conf -= motion * 0.105
    conf -= noise * 0.045
    conf -= 0.11 if stent else 0.0
    conf += 0.025 if det == "PCD" else 0.0
    # --- PLANTED SIGNAL 3: v4.1.0 regressed on Canon reconstructions.
    #     v4.1.3 fixed it. Invisible to throughput metrics; visible in ΔFFR.
    if mv == "v4.1.0" and site["make"] == "Canon":
        conf -= 0.105
    conf += random.gauss(0, 0.045)
    conf = max(0.18, min(0.995, conf))

    p_rej = 0.010 + motion * 0.050 + (0.075 if stent else 0.0) + noise * 0.018
    p_rej += 0.05 if calcium > 967 else 0.0
    rejected = random.random() < min(0.55, p_rej)
    reason = None
    if rejected:
        r = random.random()
        reason = ("motion_artifact" if r < 0.78 else
                  "contrast_opacification" if r < 0.88 else
                  "misregistration" if r < 0.95 else "coverage_incomplete")

    difficulty = 1.0 - conf
    n_edits = max(0, int(random.gauss(difficulty * 46, 6)))
    active = max(3.0, random.gauss(9.5 + difficulty * 52, 5.5))
    idle = max(0.0, random.gauss(active * 0.22, 2.4))

    n_seg = max(1, min(len(SEGMENTS), int(random.gauss(1.6 + difficulty * 6.0, 1.4))))
    bias = [(s, SEG_W[s] ** (1.0 / max(0.12, difficulty * 2.2))) for s in SEGMENTS]
    pool, touched = list(bias), []
    for _ in range(n_seg):
        tot = sum(w for _, w in pool)
        pick, c = random.uniform(0, tot), 0.0
        for j, (s, w) in enumerate(pool):
            c += w
            if pick <= c:
                touched.append(s); pool.pop(j); break
    prox_w = max(SEG_W[s] for s in touched)
    prox_touched = any(SEG_W[s] >= 0.65 for s in touched)

    ffr_pre = min(0.99, max(0.42, random.gauss(0.825, 0.095)))
    shift = abs(random.gauss(0, 0.004 + (difficulty ** 1.7) * 0.30 * prox_w))
    direction = -1 if random.random() < 0.62 else 1
    ffr_post = max(0.35, min(0.99, ffr_pre + direction * shift))
    crossed = (ffr_pre > 0.80) != (ffr_post > 0.80)
    grey = 0.75 <= ffr_post <= 0.80

    # plaque volume, mm^3. Photon-counting measures ~1/3 lower (Radiology 2025).
    tpv = max(20.0, random.gauss(760 + math.log1p(calcium) * 118, 260))
    if det == "PCD":
        tpv *= 0.66

    tat = active + idle + max(12.0, random.gauss(46, 16))

    # hazard signature matching - which risk-file entries does this case realise?
    hz = []
    if (not rejected) and prox_touched and direction > 0 and shift > 0.045 and ffr_post > 0.80:
        hz.append("H-014")                       # correction widened vessel, released as negative
    if (not rejected) and motion >= 1.6:
        hz.append("H-022")                       # analysed despite poor image quality
    if (not rejected) and stent and prox_touched and (crossed or shift > 0.04):
        hz.append("H-031")
    if (not rejected) and site["detector_switch_day"] is not None and day >= site["detector_switch_day"]:
        hz.append("H-047")

    cases.append({
        "id": i, "day": day, "site": site["id"], "det": det, "mv": mv,
        "ca": round(calcium, 1), "hr": round(hr, 1), "bmi": round(bmi, 1),
        "stent": int(stent), "nitro": int(nitro), "motion": round(motion, 2),
        "conf": round(conf, 4), "rej": int(rejected), "reason": reason,
        "edits": n_edits, "min": round(active + idle, 1),
        "segs": touched, "pre": round(ffr_pre, 4), "post": round(ffr_post, 4),
        "crossed": int(crossed), "grey": int(grey), "tpv": round(tpv, 1),
        "tat": round(tat, 1), "hz": hz,
    })

# ---------------------------------------------------------------- complaints
# Complaints arise preferentially from cases that realised a hazard, with a
# reporting lag. This is what makes the Quality lens able to traverse
# complaint -> case -> stratum -> model version.
complaints = []
cid = 0
for c in cases:
    if c["rej"]:
        continue
    p = 0.0009
    if "H-014" in c["hz"]: p += 0.075
    if "H-031" in c["hz"]: p += 0.055
    if "H-022" in c["hz"]: p += 0.012
    if c["grey"]: p += 0.006
    if random.random() < p:
        lag = int(abs(random.gauss(34, 22))) + 4
        ctype = ("false_negative" if "H-014" in c["hz"] else
                 "contraindication_missed" if "H-031" in c["hz"] else
                 "image_quality" if "H-022" in c["hz"] else "result_discrepancy")
        complaints.append({
            "id": cid, "case": c["id"], "day": min(DAYS - 1, c["day"] + lag),
            "type": ctype,
            "mdr": int(ctype in ("false_negative", "contraindication_missed") and random.random() < 0.55),
            "status": random.choice(["closed", "closed", "closed", "under_investigation"]),
            "hz": c["hz"][0] if c["hz"] else None,
        })
        cid += 1

meta = {
    "n_cases": len(cases),
    "n_sites": len(sites),
    "n_complaints": len(complaints),
    "n_mdr": sum(x["mdr"] for x in complaints),
    "days": DAYS,
    "models": MODELS,
    "hazards": [{"id": h[0], "title": h[1], "sig": h[2], "controls": h[3]} for h in HAZARDS],
    "segments": SEGMENTS,
    "scanners": [{"make": m, "model": md, "det": d} for m, md, d, _ in SCANNERS],
}

slim_sites = [{"id": s["id"], "name": s["name"], "region": s["region"], "make": s["make"],
               "model": s["model"], "det": s["detector"], "switch": s["detector_switch_day"],
               "office": int(s["office"]), "visits": s["visits"]} for s in sites]

with open("spine.js", "w", encoding="utf-8") as f:
    f.write("const META=" + json.dumps(meta) + ";\n")
    f.write("const SITES=" + json.dumps(slim_sites, separators=(",", ":")) + ";\n")
    f.write("const CASES=" + json.dumps(cases, separators=(",", ":")) + ";\n")
    f.write("const COMPLAINTS=" + json.dumps(complaints, separators=(",", ":")) + ";\n")

acc = [c for c in cases if not c["rej"]]
print(json.dumps({
    "cases": len(cases), "accepted": len(acc),
    "reject_rate": round(1 - len(acc) / len(cases), 4),
    "actionable_rate": round(sum(c["crossed"] for c in acc) / len(acc), 4),
    "complaints": len(complaints), "mdr": meta["n_mdr"],
    "hazard_matches": {h[0]: sum(1 for c in cases if h[0] in c["hz"]) for h in HAZARDS},
}, indent=2))

# --- planted signals, for the demo narrative -------------------------------
# 1. Sites 17 and 63 switch EID -> photon-counting on days 104 / 121.
#    Their total plaque volume drops ~34% with no change in patient mix.
# 2. Nine low-technique sites receive a field visit between days 55-92;
#    rejection rate falls afterwards. Closes the "did the visit work" loop.
# 3. Model v4.1.0 (day 95-147) regressed on Canon reconstructions only.
#    v4.1.3 fixed it. Throughput metrics never show it; actionable-correction
#    rate and complaint volume both do.
print("\nv4.1.0 Canon regression check:")
for mv, _ in MODELS:
    for mk in ("Canon", "Siemens"):
        sub = [c for c in acc if c["mv"] == mv and slim_sites[c["site"]]["make"] == mk]
        if len(sub) > 25:
            r = sum(c["crossed"] for c in sub) / len(sub)
            print(f"  {mv:8s} {mk:8s} n={len(sub):5d}  actionable={r*100:5.2f}%")
