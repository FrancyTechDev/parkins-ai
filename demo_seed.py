import time, random
import sqlite3
from config import DB_PATH
from db import init_db
from baseline import recompute_baseline
from metrics import compute_tsi
from aggregate import recompute_daily, recompute_weekly, recompute_monthly

def seed_demo(days: int = 7, step_sec: int = 10):
    """
    Popola DB con:
    - samples_ref (60480 righe per 7 giorni a 10s)
    - events (near_fall/freeze/sos/fall)
    - calcolo TSI (backfill)
    - aggregazioni + DPI
    """
    init_db()
    c = sqlite3.connect(DB_PATH, timeout=30)
    cur = c.cursor()

    # se ci sono già dati, non risemina
    n = cur.execute("SELECT COUNT(*) FROM samples_ref").fetchone()[0]
    if n and n > 1000:
        c.close()
        return {"seeded": False, "reason": "already_has_data", "count": n}

    start = int(time.time()) - days * 86400
    ts = start

    rows = []
    for _ in range(int(days * 86400 / step_sec)):
        ts += step_sec
        rms = 0.02 + random.random() * 0.05
        band = 0.6 + random.random() * 0.7
        peaks = random.randint(5, 35)
        tremor_f = 4.0 + random.random() * 2.0
        gsr = random.randint(450, 750)
        rows.append((ts, rms, band, peaks, tremor_f, gsr, 3.9, 0, None))

    cur.executemany(
        "INSERT OR REPLACE INTO samples_ref(ts,rms_diff,band_4_6,peaks,tremor_f,gsr,batt,qf,tsi) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        rows
    )

    # eventi demo: distribuiti sui giorni
    ev_rows = []
    for d in range(days):
        day_start = start + d * 86400

        if random.random() < 0.70:
            ev_rows.append((day_start + random.randint(8*3600, 22*3600), "near_fall", random.randint(1,2), "demo"))
        if random.random() < 0.50:
            ev_rows.append((day_start + random.randint(8*3600, 22*3600), "freeze", 1, "demo"))
        if random.random() < 0.15:
            ev_rows.append((day_start + random.randint(8*3600, 22*3600), "sos", 2, "demo"))
        if random.random() < 0.06:
            ev_rows.append((day_start + random.randint(8*3600, 22*3600), "fall", 3, "demo"))

    if ev_rows:
        cur.executemany("INSERT INTO events(ts,type,severity,meta) VALUES (?,?,?,?)", ev_rows)

    c.commit()
    c.close()

    # baseline poi backfill TSI
    recompute_baseline()

    c = sqlite3.connect(DB_PATH, timeout=30)
    cur = c.cursor()
    rows2 = cur.execute("SELECT ts,rms_diff,band_4_6,peaks,tremor_f FROM samples_ref WHERE tsi IS NULL").fetchall()

    upd = []
    for ts, rms, band, peaks, tf in rows2:
        tsi = compute_tsi(float(rms), float(band), float(peaks), float(tf) if tf is not None else None)
        upd.append((tsi, int(ts)))

    cur.executemany("UPDATE samples_ref SET tsi=? WHERE ts=?", upd)
    c.commit()
    c.close()

    # aggregazioni (con DPI + eventi)
    recompute_daily(14)
    recompute_weekly()
    recompute_monthly()

    return {"seeded": True, "samples": len(rows), "events": len(ev_rows), "tsi_filled": len(upd)}