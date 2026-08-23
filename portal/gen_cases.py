"""
Synthesizes a plausible Case Ops telemetry corpus for the Heartflow analyst workflow.

Nothing here is Heartflow data. The covariate structure is built from published
literature and the company's own disclosures:
  - median analyst processing time 26 min (S-1, Q4 2024)
  - real-world rejection 8-15%, >25% in stent-heavy cohorts
  - motion artifact causes ~78% of rejections (ADVANCE)
  - automation failure predictors: stents (p=0.001), Agatston >967 (p=0.039)
  - FFR decision threshold 0.80; grey zone 0.75-0.80

The point of the generator is that the DEPENDENCY STRUCTURE is realistic, so the
portal's views demonstrate the analysis that matters rather than showing noise.
"""
import json, math, random

random.seed(20260822)
N = 4200

SEGMENTS = ["LM", "pLAD", "mLAD", "dLAD", "D1", "pLCx", "dLCx", "OM1", "pRCA", "mRCA", "dRCA"]
# proximal segments carry more diagnostic weight - a correction there is far more
# likely to move an FFR value across threshold
SEG_WEIGHT = {"LM": 1.00, "pLAD": 0.95, "mLAD": 0.70, "dLAD": 0.30, "D1": 0.35,
              "pLCx": 0.65, "dLCx": 0.25, "OM1": 0.35, "pRCA": 0.70, "mRCA": 0.50, "dRCA": 0.22}

VENDORS = [("Siemens", 0.38, 0.92), ("GE", 0.27, 0.89),
           ("Canon", 0.20, 0.90), ("Philips", 0.15, 0.87)]

EDIT_TYPES = ["lumen_adjust", "centerline_move", "vessel_add", "ostium_reposition", "vessel_delete"]

MODEL_VERSIONS = ["v4.0.2", "v4.1.0", "v4.1.3"]


def pick_vendor():
    r = random.random()
    c = 0.0
    for name, share, quality in VENDORS:
        c += share
        if r <= c:
            return name, quality
    return VENDORS[-1][0], VENDORS[-1][2]


def lognormal(median, sigma):
    return median * math.exp(random.gauss(0, sigma))


rows = []
for i in range(N):
    # --- day index across two quarters, volume ramping ---
    day = int(abs(random.gauss(0, 1)) * 20) % 182
    quarter = 1 if day < 91 else 2

    vendor, vq = pick_vendor()
    # photon-counting share is small but rising in Q2
    pcd = random.random() < (0.045 if quarter == 1 else 0.085)
    detector = "PCD" if pcd else "EID"

    calcium = lognormal(148, 1.45)            # Agatston
    hr = random.gauss(61, 9.5)                # beta-blocked target <65
    hr_var = abs(random.gauss(0, 1)) * (2.2 if hr < 68 else 5.0)
    bmi = random.gauss(29.2, 5.6)
    stent = random.random() < 0.081
    grafts = random.random() < 0.022

    # --- image quality: motion is the dominant driver ---
    motion = (max(0.0, hr - 58) * 0.055) + hr_var * 0.16 + random.gauss(0, 0.42)
    motion += max(0.0, bmi - 30) * 0.035
    motion = max(0.0, min(3.0, motion))

    noise = max(0.0, random.gauss(1.0, 0.35) + max(0.0, bmi - 28) * 0.055 - (vq - 0.89) * 2.0)

    # --- auto-segmentation confidence ---
    conf = 0.94
    conf -= min(0.26, math.log1p(calcium / 240.0) * 0.135)
    conf -= motion * 0.105
    conf -= noise * 0.045
    conf -= 0.11 if stent else 0.0
    conf -= 0.06 if grafts else 0.0
    conf += 0.025 if pcd else 0.0          # sharper vessel walls
    conf += random.gauss(0, 0.045)
    conf = max(0.18, min(0.995, conf))

    # --- rejection gate ---
    p_reject = 0.012 + motion * 0.052 + (0.075 if stent else 0.0) + noise * 0.018
    p_reject += 0.05 if calcium > 967 else 0.0
    rejected = random.random() < min(0.55, p_reject)

    reject_reason = None
    if rejected:
        r = random.random()
        reject_reason = ("motion_artifact" if r < 0.78 else
                         "contrast_opacification" if r < 0.88 else
                         "misregistration" if r < 0.95 else "coverage_incomplete")

    # --- analyst effort ---
    difficulty = (1.0 - conf)
    n_edits = max(0, int(random.gauss(difficulty * 46, 6)))
    active_min = max(3.0, random.gauss(9.5 + difficulty * 52, 5.5))
    idle_min = max(0.0, random.gauss(active_min * 0.22, 2.4))
    total_min = active_min + idle_min
    undo = max(0, int(random.gauss(n_edits * 0.17, 2.2)))

    # Which segments were touched. This is NOT uniform: on a clean study the auto
    # segmentation is already right on the big proximal vessels and the analyst is
    # only tidying distal/minor branches. Proximal corrections are a hard-case
    # phenomenon, and they are the ones that can move an FFR value.
    n_seg = max(1, min(len(SEGMENTS), int(random.gauss(1.6 + difficulty * 6.0, 1.4))))
    seg_bias = [(s, SEG_WEIGHT[s] ** (1.0 / max(0.12, difficulty * 2.2)))
                for s in SEGMENTS]
    pool, touched = list(seg_bias), []
    for _ in range(n_seg):
        tot = sum(w for _, w in pool)
        pick = random.uniform(0, tot)
        c = 0.0
        for j, (s, w) in enumerate(pool):
            c += w
            if pick <= c:
                touched.append(s)
                pool.pop(j)
                break
    prox_weight = max(SEG_WEIGHT[s] for s in touched)

    # --- the metric that matters: did correction change the answer? ---
    # baseline FFR of the worst vessel, pre-correction
    ffr_pre = min(0.99, max(0.42, random.gauss(0.825, 0.095)))
    # Magnitude of correction-induced shift. Superlinear in difficulty: on a clean
    # study the human is confirming the model, not correcting it, and the delivered
    # value is essentially unchanged. Separation between easy and hard strata is the
    # entire premise of the automation frontier, so it has to be real here.
    shift = abs(random.gauss(0, 0.004 + (difficulty ** 1.7) * 0.30 * prox_weight))
    direction = -1 if random.random() < 0.62 else 1   # corrections usually narrow the vessel
    ffr_post = max(0.35, min(0.99, ffr_pre + direction * shift))

    crossed = (ffr_pre > 0.80) != (ffr_post > 0.80)
    grey = 0.75 <= ffr_post <= 0.80

    tat_min = total_min + max(12.0, random.gauss(46, 16))

    rows.append([
        i,                                    # 0 id
        day,                                  # 1 day
        vendor,                               # 2 vendor
        detector,                             # 3 detector
        round(calcium, 1),                    # 4 agatston
        round(hr, 1),                         # 5 heart rate
        round(bmi, 1),                        # 6 bmi
        1 if stent else 0,                    # 7 stent
        round(motion, 2),                     # 8 motion score
        round(conf, 4),                       # 9 auto-seg confidence
        1 if rejected else 0,                 # 10 rejected
        reject_reason,                        # 11 reject reason
        n_edits,                              # 12 edit count
        round(active_min, 1),                 # 13 active minutes
        round(idle_min, 1),                   # 14 idle minutes
        undo,                                 # 15 undo count
        touched,                              # 16 segments touched
        round(ffr_pre, 4),                    # 17 ffr pre-correction
        round(ffr_post, 4),                   # 18 ffr delivered
        1 if crossed else 0,                  # 19 crossed threshold
        1 if grey else 0,                     # 20 landed in grey zone
        round(tat_min, 1),                    # 21 turnaround minutes
        random.choice(MODEL_VERSIONS) if day > 60 else MODEL_VERSIONS[0],  # 22 model version
    ])

accepted = [r for r in rows if not r[10]]
crossed_n = sum(r[19] for r in accepted)

meta = {
    "n_total": len(rows),
    "n_accepted": len(accepted),
    "n_rejected": len(rows) - len(accepted),
    "reject_rate": round((len(rows) - len(accepted)) / len(rows), 4),
    "actionable_rate": round(crossed_n / len(accepted), 4),
    "median_minutes": round(sorted(r[13] + r[14] for r in accepted)[len(accepted) // 2], 1),
    "segments": SEGMENTS,
    "edit_types": EDIT_TYPES,
}

with open("data.js", "w", encoding="utf-8") as f:
    f.write("const META=" + json.dumps(meta) + ";\n")
    f.write("const CASES=" + json.dumps(rows, separators=(",", ":")) + ";\n")

print(json.dumps(meta, indent=2))
