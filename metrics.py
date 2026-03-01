from baseline import load_baseline

def _robust_z(x, med, iqr):
    return (x - med) / (iqr/1.349 + 1e-9)

def compute_tsi(rms_diff: float, band_4_6: float, peaks: float, tremor_f: float | None):
    base = load_baseline()
    if not all(k in base for k in ("rms_diff","band_4_6","peaks")):
        return None

    med_rms, iqr_rms = base["rms_diff"]
    med_b, iqr_b = base["band_4_6"]
    med_p, iqr_p = base["peaks"]

    z_rms = _robust_z(rms_diff, med_rms, iqr_rms)
    z_b = _robust_z(band_4_6, med_b, iqr_b)
    z_p = _robust_z(peaks, med_p, iqr_p)

    raw = 0.55*z_rms + 0.35*z_b + 0.10*z_p

    # confidenza freq tremore (se fuori 4–6 Hz riduci)
    if tremor_f is not None and (tremor_f < 3.8 or tremor_f > 6.2):
        raw *= 0.75

    raw = max(-2.0, min(4.0, raw))
    tsi = int(round(100 * (raw + 2.0) / 6.0))
    return max(0, min(100, tsi))