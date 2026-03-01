import time
import numpy as np
import pandas as pd
from db import connect
from config import BASELINE_DAYS

KEYS = {
    "rms_diff": "rms_diff",
    "band_4_6": "band_4_6",
    "peaks": "peaks",
}

def _median_iqr(arr: np.ndarray):
    arr = arr[~np.isnan(arr)]
    if len(arr) < 200:
        return None
    med = float(np.median(arr))
    q1 = float(np.percentile(arr, 25))
    q3 = float(np.percentile(arr, 75))
    iqr = float(q3 - q1)
    if iqr <= 1e-9:
        iqr = 1e-9
    return med, iqr

def recompute_baseline():
    c = connect()
    df = pd.read_sql(
        "SELECT rms_diff, band_4_6, peaks FROM samples_ref "
        "WHERE ts >= strftime('%s','now') - ?*86400",
        c, params=(BASELINE_DAYS,)
    )
    now = int(time.time())

    for k, col in KEYS.items():
        if df.empty:
            continue
        res = _median_iqr(df[col].to_numpy(dtype=float))
        if res is None:
            continue
        med, iqr = res
        c.execute(
            "INSERT OR REPLACE INTO baseline(key, median, iqr, updated_ts) VALUES (?,?,?,?)",
            (k, med, iqr, now)
        )

    c.commit()
    c.close()

def load_baseline():
    c = connect()
    rows = c.execute("SELECT key, median, iqr FROM baseline").fetchall()
    c.close()
    out = {}
    for k, med, iqr in rows:
        out[k] = (float(med), float(iqr))
    return out