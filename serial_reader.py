import json, time
import serial
from config import SERIAL_PORT, BAUD
from db import init_db, connect
from metrics import compute_tsi

def run():
    init_db()
    ser = serial.Serial(SERIAL_PORT, BAUD, timeout=1)

    c = connect()
    c.execute("PRAGMA journal_mode=WAL;")

    while True:
        line = ser.readline().decode(errors="ignore").strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except:
            continue

        if msg.get("type") != "ref":
            continue

        ts = int(msg["ts"])
        rms = float(msg["rms_diff"])
        band = float(msg["band_4_6"])
        peaks = float(msg["peaks"])
        tremor_f = msg.get("tremor_f")
        tremor_f = float(tremor_f) if tremor_f is not None else None
        gsr = float(msg.get("gsr", 0))
        batt = float(msg.get("batt", 0))
        qf = int(msg.get("qf", 0))

        tsi = compute_tsi(rms, band, peaks, tremor_f)

        c.execute(
            "INSERT OR REPLACE INTO samples_ref(ts,rms_diff,band_4_6,peaks,tremor_f,gsr,batt,qf,tsi) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (ts, rms, band, peaks, tremor_f, gsr, batt, qf, tsi)
        )
        c.commit()

if __name__ == "__main__":
    run()