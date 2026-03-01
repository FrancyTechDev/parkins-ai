import time, random
from db import init_db, connect
from baseline import recompute_baseline
from aggregate import recompute_daily, recompute_weekly, recompute_monthly
from metrics import compute_tsi

def seed_demo(days: int = 7, step_sec: int = 10):
    """
    Popola il DB con dati simulati (7 giorni) SOLO se il DB è vuoto.
    Poi calcola baseline, TSI e aggregazioni.
    """
    init_db()
    c = connect()
    c.execute("PRAGMA journal_mode=WAL;")

    # Se già ci sono dati, non rigenerare
    n = c.execute("SELECT COUNT(*) FROM samples_ref").fetchone()[0]
    if n and n > 1000:
        c.close()
        return {"seeded": False, "reason": "already_has_data", "count": n}

    ts = int(time.time()) - days * 86400

    rows = []
    for _ in range(int(days * 86400 / step_sec)):
        ts += step_sec
        rms = 0.02 + random.random() * 0.05
        band = 0.6 + random.random() * 0.7
        peaks = random.randint(5, 35)
        tremor_f = 4.0 + random.random() * 2.0
        gsr = random.randint(450, 750)

        rows.append((ts, rms, band, peaks, tremor_f, gsr, 3.9, 0, None))

    c.executemany(
        "INSERT OR REPLACE INTO samples_ref(ts,rms_diff,band_4_6,peaks,tremor_f,gsr,batt,qf,tsi) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        rows
    )
    c.commit()
    c.close()

    # Baseline
    recompute_baseline()

    # Backfill TSI (usa metrics.compute_tsi che usa la baseline)
    c = connect()
    cur = c.cursor()
    cur.execute("SELECT ts, rms_diff, band_4_6, peaks, tremor_f FROM samples_ref WHERE tsi IS NULL")
    upd = []
    for ts, rms, band, peaks, tf in cur.fetchall():
        tsi = compute_tsi(float(rms), float(band), float(peaks), float(tf) if tf is not None else None)
        upd.append((tsi, int(ts)))

    cur.executemany("UPDATE samples_ref SET tsi=? WHERE ts=?", upd)
    c.commit()
    c.close()

    # Aggregazioni
    recompute_daily(days)
    recompute_weekly()
    recompute_monthly()

    return {"seeded": True, "count": len(rows)}