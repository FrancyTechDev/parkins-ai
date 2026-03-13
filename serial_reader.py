import json, time
import serial
from config import SERIAL_PORT, BAUD, AUTO_TSI, AUTO_PEAKS, AUTO_TREMOR_HZ
from db import (
    init_db, connect, get_setting, insert_history_sample,
    insert_event, insert_telemetry_sample
)
from metrics import compute_tsi


def sev_to_int(sev):
    if isinstance(sev, (int, float)):
        return int(sev)

    s = str(sev).lower().strip()
    if s in ("info", "low", "soft"):
        return 1
    if s in ("warning", "medium"):
        return 2
    if s in ("critical", "high", "strong", "emergency"):
        return 3
    return 1


def run():
    init_db()
    ser = serial.Serial(SERIAL_PORT, BAUD, timeout=1)

    c = connect()
    c.execute("PRAGMA journal_mode=WAL;")

    last_mode_check = 0
    ingest_mode = "on"

    while True:
        line = ser.readline().decode(errors="ignore").strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except Exception:
            continue

        msg_type = msg.get("type")

        # =========================
        # REF -> samples_ref + history
        # =========================
        if msg_type == "ref":
            ts = int(msg["ts"])
            rms = float(msg["rms_diff"])
            rms2 = float(msg["rms2"]) if msg.get("rms2") is not None else None
            band = float(msg["band_4_6"])
            peaks = float(msg["peaks"])
            tremor_f = msg.get("tremor_f")
            tremor_f = float(tremor_f) if tremor_f is not None else None
            gsr = float(msg.get("gsr", 0))
            batt = float(msg.get("batt", 0))
            qf = int(msg.get("qf", 0))

            tsi = compute_tsi(rms, band, peaks, tremor_f)

            now = time.time()
            if now - last_mode_check > 2:
                ingest_mode = get_setting("ingest_mode", "on")
                last_mode_check = now

            important = (
                (tsi is not None and tsi >= AUTO_TSI) or
                (peaks is not None and peaks >= AUTO_PEAKS) or
                (tremor_f is not None and tremor_f >= AUTO_TREMOR_HZ)
            )

            if ingest_mode == "off":
                continue
            if ingest_mode == "auto" and not important:
                continue

            c.execute(
                "INSERT OR REPLACE INTO samples_ref(ts,rms_diff,rms2,band_4_6,peaks,tremor_f,gsr,batt,qf,tsi) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ts, rms, rms2, band, peaks, tremor_f, gsr, batt, qf, tsi)
            )
            c.commit()

            insert_history_sample(ts, rms, rms2, band, peaks, tremor_f, gsr, batt, qf, tsi)
            continue

        # =========================
        # TELEMETRY -> telemetry
        # =========================
        if msg_type == "telemetry":
            ts = int(msg.get("epoch", time.time()))
            rms1 = float(msg.get("rms1", 0))
            rms2 = float(msg.get("rms2", 0))
            rms_diff = float(msg.get("rms_diff", abs(rms1 - rms2)))
            freq = float(msg.get("freq", 0))
            band_4_6 = float(msg.get("band_4_6", 1.0 if 4.0 <= freq <= 6.0 else 0.0))
            peaks = float(msg.get("peaks", 0))
            bai = float(msg.get("bai", 0))
            ci = float(msg.get("ci", 0))
            tvi = float(msg.get("tvi", 0))
            delay_ms = float(msg.get("delay", 0))
            neuro = float(msg.get("neuro", 0))
            acc = float(msg.get("acc", 0))
            gyro = float(msg.get("gyro", 0))
            gsr = float(msg.get("gsr", 0))
            mode = int(msg.get("mode", 0))
            m1 = int(msg.get("m1", 0))
            m2 = int(msg.get("m2", 0))
            batt = float(msg.get("batt", 0))
            qf = int(msg.get("qf", 0))

            insert_telemetry_sample(
                ts, rms1, rms2, rms_diff, freq, band_4_6, peaks,
                bai, ci, tvi, delay_ms, neuro, acc, gyro, gsr,
                mode, m1, m2, batt, qf
            )
            continue

        # =========================
        # EVENT -> events
        # =========================
        if msg_type == "event":
            ts = int(msg.get("ts", time.time()))
            ev_type = msg.get("event", "unknown")
            severity = sev_to_int(msg.get("severity", 1))
            message = str(msg.get("message", ""))

            # classificazione base
            category = "system"
            subtype = str(ev_type)

            if "wifi" in ev_type:
                category = "connectivity"
            elif "sos" in ev_type:
                category = "safety"
            elif "sensor" in ev_type:
                category = "sensor"
            elif "threshold" in ev_type:
                category = "settings"
            elif "fall" in ev_type:
                category = "safety"

            meta = json.dumps(msg, ensure_ascii=False)

            insert_event(
                ts=ts,
                ev_type=ev_type,
                severity=severity,
                meta=meta,
                category=category,
                subtype=subtype,
                message=message
            )
            continue


if __name__ == "__main__":
    run()
