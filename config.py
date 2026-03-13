import os


if os.getenv("RENDER"):
    DEFAULT_DB = "/tmp/db.sqlite"
else:
    # Keep DB out of repo on Linux to avoid corruption during git pulls
    if os.name == "nt":
        DEFAULT_DB = "db.sqlite"
    else:
        DEFAULT_DB = "/var/lib/parkins/db.sqlite"

DB_PATH = os.getenv("DB_PATH", DEFAULT_DB)


# Windows: "COM3"
# Raspberry: "/dev/ttyACM0"

SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyACM0")
BAUD = int(os.getenv("BAUD", "115200"))


# Se DEMO_MODE=1 genera dati simulati all'avvio
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"


BASELINE_DAYS = int(os.getenv("BASELINE_DAYS", "7"))

BASELINE_REFRESH_SEC = int(os.getenv("BASELINE_REFRESH_SEC", "600"))   # 10 min
AGG_REFRESH_SEC = int(os.getenv("AGG_REFRESH_SEC", "300"))            # 5 min
FORECAST_REFRESH_SEC = int(os.getenv("FORECAST_REFRESH_SEC", "900"))  # 15 min


TSI_MED = int(os.getenv("TSI_MED", "55"))
TSI_HIGH = int(os.getenv("TSI_HIGH", "70"))
TSI_SEVERE = int(os.getenv("TSI_SEVERE", "85"))

# Auto-save thresholds (for ingest_mode=auto)
AUTO_TSI = float(os.getenv("AUTO_TSI", "2.5"))
AUTO_PEAKS = int(os.getenv("AUTO_PEAKS", "12"))
AUTO_TREMOR_HZ = float(os.getenv("AUTO_TREMOR_HZ", "4.5"))
