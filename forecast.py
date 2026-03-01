import numpy as np
import pandas as pd
from db import connect

def forecast_72h(days_back: int = 7):
    c = connect()
    df = pd.read_sql(
        "SELECT ts, tsi FROM samples_ref "
        "WHERE tsi IS NOT NULL AND ts >= strftime('%s','now') - ?*86400 "
        "ORDER BY ts ASC",
        c, params=(days_back,)
    )
    c.close()

    if df.empty:
        return None

    # media oraria
    df["dt"] = pd.to_datetime(df["ts"], unit="s")
    df = df.set_index("dt").sort_index()
    hourly = df["tsi"].resample("1h").mean().dropna()
    if len(hourly) < 12:
        return None

    y = hourly.to_numpy(dtype=float)
    x = np.arange(len(y))

    # trend lineare + intervallo predittivo grezzo
    m, b = np.polyfit(x, y, 1)
    pred = float(m*(len(y)+72) + b)

    resid = y - (m*x + b)
    sigma = float(np.std(resid)) if len(resid) > 5 else float(np.std(y))

    return {
        "horizon_h": 72,
        "pred": pred,
        "lo": pred - 1.28*sigma,   # ~80%
        "hi": pred + 1.28*sigma,
        "method": f"linear_hourly_{days_back}d_80pi",
        "hours_used": int(len(hourly))
    }