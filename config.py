DB_PATH = "db.sqlite"

# Windows: "COM3"  |  Raspberry: "/dev/ttyACM0"
SERIAL_PORT = "COM3"
BAUD = 115200

# Aggiornamenti
BASELINE_DAYS = 7
BASELINE_REFRESH_SEC = 600   # 10 min
AGG_REFRESH_SEC = 300        # 5 min
FORECAST_REFRESH_SEC = 900   # 15 min

# Soglie indice (TSI)
TSI_MED = 55
TSI_HIGH = 70
TSI_SEVERE = 85