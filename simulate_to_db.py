import time, random
from db import init_db, connect
from baseline import recompute_baseline
from aggregate import recompute_daily, recompute_weekly, recompute_monthly

init_db()
c = connect()
c.execute("PRAGMA journal_mode=WAL;")

ts = int(time.time()) - 7*86400  # fingi 7 giorni di storico

# genera 7 giorni di dati (uno ogni 10 secondi -> ~60k record)
for i in range(7*24*60*6):
    ts += 10
    rms = 0.02 + random.random()*0.05
    band = 0.6 + random.random()*0.7
    peaks = random.randint(5, 35)
    tremor_f = 4.0 + random.random()*2.0
    gsr = random.randint(450, 750)

    # tsi verrà calcolato dopo baseline: per ora metti None
    c.execute(
        "INSERT OR REPLACE INTO samples_ref(ts,rms_diff,band_4_6,peaks,tremor_f,gsr,batt,qf,tsi) VALUES (?,?,?,?,?,?,?,?,?)",
        (ts, rms, band, peaks, tremor_f, gsr, 3.9, 0, None)
    )

c.commit()
c.close()

# costruisci baseline e ricalcola aggregazioni
recompute_baseline()
recompute_daily(7)
recompute_weekly()
recompute_monthly()

print("OK: DB popolato + baseline + aggregazioni calcolate")