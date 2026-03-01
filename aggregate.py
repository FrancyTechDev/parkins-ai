import time
import numpy as np
import pandas as pd
from db import connect
from config import TSI_HIGH
from progression import compute_dpi_row

def _p90(x):
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return None
    return float(np.percentile(x, 90))

def recompute_daily(days: int = 7):
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

    ev = pd.read_sql(
        """
        SELECT date(ts,'unixepoch') as day,
               SUM(CASE WHEN type='fall' THEN 1 ELSE 0 END) as falls,
               SUM(CASE WHEN type='near_fall' THEN 1 ELSE 0 END) as near_falls,
               SUM(CASE WHEN type='freeze' THEN 1 ELSE 0 END) as freezes,
               SUM(CASE WHEN type='sos' THEN 1 ELSE 0 END) as sos
        FROM events
        WHERE ts >= strftime('%s','now') - ?*86400
        GROUP BY day
        """,
        c, params=(days,)
    )

    ev_map = {}
    if not ev.empty:
        for _, r in ev.iterrows():
            ev_map[r["day"]] = (
                int(r["falls"] or 0),
                int(r["near_falls"] or 0),
                int(r["freezes"] or 0),
                int(r["sos"] or 0),
            )

    now = int(time.time())

    for day, g in df.groupby("day"):
        tsi_mean = float(g["tsi"].mean())
        tsi_p90 = _p90(g["tsi"].to_numpy(dtype=float))
        tremor_minutes = float((g["tsi"] >= TSI_HIGH).mean() * 24 * 60)  # stima grezza
        sample_count = int(len(g))

        falls, near_falls, freezes, sos = ev_map.get(day, (0, 0, 0, 0))

        dpi = compute_dpi_row(tsi_mean, tremor_minutes, falls, near_falls, freezes, sos)

        c.execute(
            """
            INSERT OR REPLACE INTO daily_agg(
              day, tsi_mean, tsi_p90, tremor_minutes, sample_count,
              falls, near_falls, freezes, sos,
              dpi,
              updated_ts
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (day, tsi_mean, tsi_p90, tremor_minutes, sample_count,
             falls, near_falls, freezes, sos,
             dpi,
             now)
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