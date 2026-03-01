import numpy as np
import pandas as pd
from db import connect

DPI_SEVERE = 85

def load_daily(limit=90):
    c = connect()
    df = pd.read_sql("""
      SELECT day, tsi_mean, tsi_p90, tremor_minutes, sample_count,
             COALESCE(falls,0) as falls,
             COALESCE(near_falls,0) as near_falls,
             COALESCE(freezes,0) as freezes,
             COALESCE(sos,0) as sos,
             dpi
      FROM daily_agg
      ORDER BY day ASC
    """, c)
    c.close()
    if df.empty:
        return df
    if len(df) > limit:
        df = df.iloc[-limit:].copy()
    return df

def _safe(v, default=0.0):
    return default if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)

def compute_dpi_row(tsi_mean, tremor_minutes, falls, near_falls, freezes, sos):
    tsi_mean = _safe(tsi_mean)
    tremor_minutes = _safe(tremor_minutes)
    falls = int(_safe(falls))
    near_falls = int(_safe(near_falls))
    freezes = int(_safe(freezes))
    sos = int(_safe(sos))

    tm = min(180.0, tremor_minutes) / 180.0
    event_score = (3.0*falls + 1.5*near_falls + 1.0*freezes + 2.0*sos)
    ev = np.tanh(event_score / 3.0)

    dpi = 0.60*tsi_mean + 0.15*(tm*100.0) + 0.25*(ev*100.0)
    return float(max(0.0, min(100.0, dpi)))

def compute_dpi_series(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    if "dpi" not in df.columns or df["dpi"].isna().all():
        df["dpi"] = df.apply(lambda r: compute_dpi_row(
            r.get("tsi_mean"), r.get("tremor_minutes"),
            r.get("falls"), r.get("near_falls"),
            r.get("freezes"), r.get("sos")
        ), axis=1)
    else:
        df["dpi"] = df["dpi"].astype(float)
    return df

def _trend(y: np.ndarray):
    x = np.arange(len(y), dtype=float)
    m, b = np.polyfit(x, y, 1)
    resid = y - (m*x + b)
    sigma = float(np.std(resid)) if len(resid) > 2 else float(np.std(y))
    return float(m), float(b), sigma

def progression_state(df: pd.DataFrame):
    if df.empty or len(df) < 7:
        return {"status":"insufficient_data", "message":"Servono almeno 7 giorni in daily_agg."}

    y = df["dpi"].to_numpy(dtype=float)
    m, b, sigma = _trend(y)

    last7 = df.iloc[-7:]
    ev7 = int(last7["falls"].sum() + last7["near_falls"].sum() + last7["freezes"].sum() + last7["sos"].sum())
    falls7 = int(last7["falls"].sum())

    if falls7 >= 1 or m > 0.25:
        state = "peggioramento_rapido"
    elif ev7 >= 2 or m > 0.08:
        state = "peggioramento_lieve"
    else:
        state = "stabile"

    return {
        "status":"ok",
        "state": state,
        "dpi_current": float(y[-1]),
        "dpi_trend_per_day": m,
        "volatility": sigma,
        "events_last7": ev7,
        "falls_last7": falls7
    }

def risk_30_90(df: pd.DataFrame):
    st = progression_state(df)
    if st.get("status") != "ok":
        return {"status":"insufficient_data"}

    m = st["dpi_trend_per_day"]
    ev7 = st["events_last7"]
    falls7 = st["falls_last7"]
    current = st["dpi_current"]

    score = 0.0
    score += min(1.0, max(0.0, (m / 0.30))) * 0.55
    score += min(1.0, ev7 / 6.0) * 0.25
    score += (1.0 if falls7 >= 1 else 0.0) * 0.15
    score += min(1.0, current / 100.0) * 0.05

    r30 = float(max(0.0, min(100.0, 100.0 * score)))
    r90 = float(max(0.0, min(100.0, 100.0 * (0.75*score + 0.25*min(1.0, score*1.2)))))

    return {"status":"ok", "risk_30d": r30, "risk_90d": r90}

def time_to_severe(df: pd.DataFrame, threshold: float = DPI_SEVERE):
    if df.empty or len(df) < 14:
        return {"status":"insufficient_data", "message":"Servono idealmente >= 14 giorni."}

    y = df["dpi"].to_numpy(dtype=float)
    m, b, sigma = _trend(y)
    current = float(y[-1])

    if m <= 0:
        return {"status":"ok", "reachable": False, "reason":"trend_non_crescente", "current_dpi": current, "trend": m}

    days_est = (threshold - current) / m
    lo = (threshold - (current + sigma)) / m
    hi = (threshold - (current - sigma)) / m
    lo = float(max(0.0, lo))
    hi = float(max(0.0, hi))

    return {
        "status":"ok", "reachable": True, "threshold": float(threshold),
        "current_dpi": current, "trend": m,
        "days_est": float(days_est), "days_range": [lo, hi]
    }

def full_progression():
    df = load_daily()
    if df.empty:
        return {"status":"insufficient_data"}

    df = compute_dpi_series(df)
    st = progression_state(df)
    rk = risk_30_90(df)
    tts = time_to_severe(df)
    return {"status":"ok", "state": st, "risk": rk, "time_to_severe_dpi": tts, "dpi_severe_threshold": DPI_SEVERE}