import sqlite3
from baseline import recompute_baseline, load_baseline

DB = "db.sqlite"

def robust_z(x, med, iqr):
    return (x - med) / (iqr/1.349 + 1e-9)

def compute_tsi_row(rms_diff, band_4_6, peaks, tremor_f, base):
    med_rms, iqr_rms = base["rms_diff"]
    med_band, iqr_band = base["band_4_6"]
    med_peaks, iqr_peaks = base["peaks"]

    z_rms = robust_z(rms_diff, med_rms, iqr_rms)
    z_band = robust_z(band_4_6, med_band, iqr_band)
    z_peaks = robust_z(peaks, med_peaks, iqr_peaks)

    raw = 0.55*z_rms + 0.35*z_band + 0.10*z_peaks

    if tremor_f is not None and (tremor_f < 3.8 or tremor_f > 6.2):
        raw *= 0.75

    raw = max(-2.0, min(4.0, raw))
    tsi = int(round(100 * (raw + 2.0) / 6.0))
    return max(0, min(100, tsi))

def main():
    # 1) crea/aggiorna baseline dai dati presenti
    recompute_baseline()
    base = load_baseline()

    if not all(k in base for k in ("rms_diff", "band_4_6", "peaks")):
        raise SystemExit("Baseline non pronta: servono abbastanza dati per median+IQR.")

    con = sqlite3.connect(DB)
    cur = con.cursor()

    cur.execute("SELECT ts, rms_diff, band_4_6, peaks, tremor_f FROM samples_ref WHERE tsi IS NULL")
    rows = cur.fetchall()
    print("Rows to backfill:", len(rows))

    upd = []
    for ts, rms, band, peaks, tf in rows:
        tsi = compute_tsi_row(float(rms), float(band), float(peaks), tf, base)
        upd.append((tsi, int(ts)))

    cur.executemany("UPDATE samples_ref SET tsi=? WHERE ts=?", upd)
    con.commit()
    con.close()
    print("Backfill done.")

if __name__ == "__main__":
    main()