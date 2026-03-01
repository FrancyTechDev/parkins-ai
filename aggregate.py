import time
import numpy as np
import pandas as pd
from db import connect
from config import TSI_HIGH

def _p90(x):
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return None
    return float(np.percentile(x, 90))

def recompute_daily(days=7):
    c = connect()
    df = pd.read_sql(
        "SELECT ts, tsi FROM samples_ref WHERE tsi IS NOT NULL "
        "AND ts >= strftime('%s','now') - ?*86400",
        c, params=(days,)
    )
    if df.empty:
        c.close()
        return

    df["day"] = pd.to_datetime(df["ts"], unit="s").dt.strftime("%Y-%m-%d")

    now = int(time.time())
    for day, g in df.groupby("day"):
        tsi_mean = float(g["tsi"].mean())
        tsi_p90 = _p90(g["tsi"].to_numpy(dtype=float))
        tremor_minutes = float((g["tsi"] >= TSI_HIGH).mean() * 24*60)  # stima grezza
        sample_count = int(len(g))
        c.execute(
            "INSERT OR REPLACE INTO daily_agg(day,tsi_mean,tsi_p90,tremor_minutes,sample_count,updated_ts) "
            "VALUES (?,?,?,?,?,?)",
            (day, tsi_mean, tsi_p90, tremor_minutes, sample_count, now)
        )
    c.commit()
    c.close()

def recompute_weekly():
    c = connect()
    df = pd.read_sql("SELECT day, tsi_mean FROM daily_agg ORDER BY day", c)
    if df.empty:
        c.close()
        return

    df["date"] = pd.to_datetime(df["day"])
    df["week"] = df["date"].dt.strftime("%Y-W%U")

    now = int(time.time())
    for w, g in df.groupby("week"):
        x = np.arange(len(g))
        y = g["tsi_mean"].to_numpy(dtype=float)
        trend = float(np.polyfit(x, y, 1)[0]) if len(y) >= 3 else 0.0
        tsi_mean = float(np.mean(y))
        high_days = int((y >= 70).sum())
        c.execute(
            "INSERT OR REPLACE INTO weekly_agg(week,tsi_mean,tsi_trend,high_days,updated_ts) "
            "VALUES (?,?,?,?,?)",
            (w, tsi_mean, trend, high_days, now)
        )
    c.commit()
    c.close()

def recompute_monthly():
    c = connect()
    df = pd.read_sql("SELECT day, tsi_mean FROM daily_agg ORDER BY day", c)
    if df.empty:
        c.close()
        return
    df["date"] = pd.to_datetime(df["day"])
    df["month"] = df["date"].dt.strftime("%Y-%m")

    now = int(time.time())
    for m, g in df.groupby("month"):
        x = np.arange(len(g))
        y = g["tsi_mean"].to_numpy(dtype=float)
        trend = float(np.polyfit(x, y, 1)[0]) if len(y) >= 5 else 0.0
        tsi_mean = float(np.mean(y))
        c.execute(
            "INSERT OR REPLACE INTO monthly_agg(month,tsi_mean,tsi_trend,updated_ts) VALUES (?,?,?,?)",
            (m, tsi_mean, trend, now)
        )
    c.commit()
    c.close()