"""Plain least-squares workload forecast. Deliberately simple ML.

Question: how many minutes of analysis work will each analyst resolve per day
next week? Model: per-analyst ordinary least squares on
[intercept, day-of-week one-hots, linear trend] - numpy.linalg.lstsq, nothing
else. Honesty budget: the last 14 days are held out; we report the model's MAE
next to a naive weekday-mean baseline, because a forecaster that cannot beat
"what do Mondays usually look like" should say so. Weekends the analyst never
worked stay at their (near-zero) fitted level rather than being clamped.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

HOLDOUT_DAYS = 14
FORECAST_DAYS = 7


def _design(days: list[date], t0: date) -> np.ndarray:
    """[1, dow_1..dow_6, t] - Monday is the reference weekday."""
    rows = []
    for d in days:
        dow = np.zeros(6)
        if d.weekday() > 0:
            dow[d.weekday() - 1] = 1.0
        rows.append(np.concatenate(([1.0], dow, [(d - t0).days / 30.0])))
    return np.array(rows)


def forecast_analyst(daily: dict[date, float]) -> dict:
    """daily: resolved minutes per calendar day (missing days count as 0 within
    the observed span). Returns history tail, 7-day forecast, and holdout MAEs."""
    if len(daily) < 21:
        return {"insufficient_history": True, "days_observed": len(daily)}
    d0, d1 = min(daily), max(daily)
    days = [d0 + timedelta(i) for i in range((d1 - d0).days + 1)]
    y = np.array([daily.get(d, 0.0) for d in days])

    cut = len(days) - HOLDOUT_DAYS
    Xtr, ytr = _design(days[:cut], d0), y[:cut]
    beta, *_ = np.linalg.lstsq(Xtr, ytr, rcond=None)

    Xho = _design(days[cut:], d0)
    pred_ho = np.clip(Xho @ beta, 0, None)
    mae_model = float(np.mean(np.abs(pred_ho - y[cut:])))

    # naive baseline: mean minutes per weekday over the training span
    wd_mean = {wd: float(np.mean([v for d, v in zip(days[:cut], ytr)
                                  if d.weekday() == wd]) or 0.0)
               for wd in range(7)}
    naive_ho = np.array([wd_mean[d.weekday()] for d in days[cut:]])
    mae_naive = float(np.mean(np.abs(naive_ho - y[cut:])))

    future = [d1 + timedelta(i + 1) for i in range(FORECAST_DAYS)]
    pred = np.clip(_design(future, d0) @ beta, 0, None)

    return {
        "history": [{"day": d.isoformat(), "minutes": round(float(v), 1)}
                    for d, v in list(zip(days, y))[-28:]],
        "forecast": [{"day": d.isoformat(), "minutes": round(float(v), 1)}
                     for d, v in zip(future, pred)],
        "mae_model": round(mae_model, 1),
        "mae_naive": round(mae_naive, 1),
        "holdout_days": HOLDOUT_DAYS,
        "method": "OLS on [1, weekday one-hots, monthly trend]; "
                  "last 14 days held out; baseline = weekday mean",
    }


def workload(cur) -> dict:
    """Forecast for every analyst, from the resolved-ticket history."""
    cur.execute("""
        SELECT analyst_id, resolved_at::date AS day,
               sum(actual_min)::float AS minutes
        FROM ticket WHERE status = 'resolved' AND analyst_id IS NOT NULL
        GROUP BY 1, 2""")
    per: dict[int, dict[date, float]] = {}
    for r in cur.fetchall():
        per.setdefault(r["analyst_id"], {})[r["day"]] = r["minutes"]
    cur.execute("SELECT analyst_id, name, capacity_min_day FROM analyst ORDER BY analyst_id")
    out = []
    for a in cur.fetchall():
        f = forecast_analyst(per.get(a["analyst_id"], {}))
        f.update({"analyst_id": a["analyst_id"], "name": a["name"],
                  "capacity_min_day": a["capacity_min_day"]})
        out.append(f)
    return {"analysts": out}


# ------------------------------------------------------------- change-level model
# Predict the LEVEL OF CHANGE a correction will make to the 3D artifact
# (binary blocks touched, %) from the hospital and the device alone.
#
# Feature governance, deliberate and testable: site_class, region, scanner
# make, detector generation. NO analyst identity, NO patient demographics -
# a change-level model must never become an analyst-surveillance model or a
# patient-profiling model.
CHANGE_FEATURES = ["site_class", "region", "make", "detector"]
EXCLUDED_BY_POLICY = ["analyst identity", "patient demographics"]


def change_level_model(cur) -> dict:
    cur.execute("""
        SELECT g.blocks_changed_pct AS y, h.site_class, h.region, d.make, d.detector
        FROM geometry_delta g
        JOIN ticket t USING (ticket_id)
        JOIN device d ON d.device_id = t.device_id
        JOIN hospital h ON h.hospital_id = t.hospital_id""")
    rows_ = cur.fetchall()
    if len(rows_) < 60:
        return {"insufficient_data": True, "n": len(rows_)}

    levels = {f: sorted({r[f] for r in rows_}) for f in CHANGE_FEATURES}
    names, cols = ["intercept"], []
    for f in CHANGE_FEATURES:
        for lv in levels[f][1:]:                      # first level = reference
            names.append(f"{f}={lv}")
            cols.append((f, lv))
    X = np.array([[1.0] + [1.0 if r[f] == lv else 0.0 for f, lv in cols]
                  for r in rows_])
    y = np.array([float(r["y"]) for r in rows_])

    rs = np.random.default_rng(7)
    idx = rs.permutation(len(y))
    cut = int(len(y) * 0.75)
    tr, ho = idx[:cut], idx[cut:]
    beta, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
    mae_model = float(np.mean(np.abs(np.clip(X[ho] @ beta, 0, 100) - y[ho])))
    mae_naive = float(np.mean(np.abs(y[tr].mean() - y[ho])))

    # per device-context prediction table: what level of change to EXPECT
    groups: dict[tuple, list[float]] = {}
    for r, yy in zip(rows_, y):
        groups.setdefault((r["make"], r["detector"], r["site_class"]), []).append(yy)
    table = []
    for (make, det, sc), ys in sorted(groups.items()):
        xrow = np.array([1.0] + [1.0 if (f == "make" and lv == make)
                                 or (f == "detector" and lv == det)
                                 or (f == "site_class" and lv == sc) else 0.0
                                 for f, lv in cols])
        table.append({"make": make, "detector": det, "site_class": sc,
                      "n": len(ys), "actual_mean": round(float(np.mean(ys)), 2),
                      "predicted": round(float(np.clip(xrow @ beta, 0, 100)), 2)})
    table.sort(key=lambda r: -r["predicted"])

    return {
        "n": len(rows_), "target": "blocks_changed_pct (binary level of change)",
        "features_used": CHANGE_FEATURES,
        "excluded_by_policy": EXCLUDED_BY_POLICY,
        "coefficients": {n: round(float(b), 2) for n, b in zip(names, beta)},
        "mae_model": round(mae_model, 2), "mae_naive": round(mae_naive, 2),
        "holdout_frac": 0.25,
        "groups": table,
        "method": "OLS on one-hot hospital+device features; 25% random holdout; "
                  "baseline = global mean",
    }
