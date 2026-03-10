import sqlite3
import time
import datetime as dt
from config import DB_PATH


def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        pass
    return conn


def init_db():
    c = connect()
    cur = c.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS samples_ref (
      ts INTEGER PRIMARY KEY,
      rms_diff REAL NOT NULL,
      band_4_6 REAL NOT NULL,
      peaks REAL NOT NULL,
      tremor_f REAL,
      gsr REAL,
      batt REAL,
      qf INTEGER DEFAULT 0,
      tsi REAL
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples_ref(ts);")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS telemetry (
      ts INTEGER PRIMARY KEY,
      rms1 REAL,
      rms2 REAL,
      rms_diff REAL,
      freq REAL,
      band_4_6 REAL,
      peaks REAL,
      bai REAL,
      ci REAL,
      tvi REAL,
      delay_ms REAL,
      neuro REAL,
      acc REAL,
      gyro REAL,
      gsr REAL,
      mode INTEGER,
      m1 INTEGER,
      m2 INTEGER,
      batt REAL,
      qf INTEGER DEFAULT 0
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(ts);")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS baseline (
      key TEXT PRIMARY KEY,
      median REAL NOT NULL,
      iqr REAL NOT NULL,
      updated_ts INTEGER NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_profile (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_ts INTEGER NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_feedback (
      day TEXT PRIMARY KEY,
      score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
      note TEXT,
      created_ts INTEGER NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      type TEXT NOT NULL,
      severity INTEGER DEFAULT 1,
      meta TEXT DEFAULT "",
      category TEXT DEFAULT "sensor",
      subtype TEXT DEFAULT "",
      message TEXT DEFAULT ""
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_agg (
      day TEXT PRIMARY KEY,
      tsi_mean REAL,
      tsi_p90 REAL,
      tremor_minutes REAL,
      sample_count INTEGER,
      falls INTEGER DEFAULT 0,
      near_falls INTEGER DEFAULT 0,
      freezes INTEGER DEFAULT 0,
      sos INTEGER DEFAULT 0,
      dpi REAL,
      updated_ts INTEGER NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_agg (
      week TEXT PRIMARY KEY,
      tsi_mean REAL,
      tsi_trend REAL,
      high_days INTEGER,
      updated_ts INTEGER NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS monthly_agg (
      month TEXT PRIMARY KEY,
      tsi_mean REAL,
      tsi_trend REAL,
      updated_ts INTEGER NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS forecasts (
      created_ts INTEGER NOT NULL,
      horizon_h INTEGER NOT NULL,
      pred REAL,
      lo REAL,
      hi REAL,
      method TEXT,
      PRIMARY KEY(created_ts, horizon_h)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_ts INTEGER NOT NULL
    )
    """)
    cur.execute(
        "INSERT OR IGNORE INTO app_settings(key,value,updated_ts) VALUES (?,?,?)",
        ("ingest_mode", "on", int(time.time()))
    )

    c.commit()
    c.close()

    try:
        _ensure_events_columns()
    except Exception:
        pass


def get_setting(key, default=None):
    c = connect()
    cur = c.cursor()
    cur.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = cur.fetchone()
    c.close()
    if row is None:
        return default
    return row[0]


def set_setting(key, value):
    c = connect()
    cur = c.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO app_settings(key,value,updated_ts) VALUES (?,?,?)",
        (key, str(value), int(time.time()))
    )
    c.commit()
    c.close()


def _ensure_events_columns():
    c = connect()
    cur = c.cursor()
    cur.execute("PRAGMA table_info(events)")
    cols = {r[1] for r in cur.fetchall()}

    if "category" not in cols:
        cur.execute("ALTER TABLE events ADD COLUMN category TEXT DEFAULT 'sensor'")
    if "subtype" not in cols:
        cur.execute("ALTER TABLE events ADD COLUMN subtype TEXT DEFAULT ''")
    if "message" not in cols:
        cur.execute("ALTER TABLE events ADD COLUMN message TEXT DEFAULT ''")

    c.commit()
    c.close()


def history_table_for_ts(ts: int):
    day = dt.datetime.fromtimestamp(int(ts)).strftime("%Y_%m_%d")
    return f"history_{day}"


def ensure_history_table(table_name: str):
    c = connect()
    cur = c.cursor()
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
      ts INTEGER PRIMARY KEY,
      rms_diff REAL NOT NULL,
      band_4_6 REAL NOT NULL,
      peaks REAL NOT NULL,
      tremor_f REAL,
      gsr REAL,
      batt REAL,
      qf INTEGER DEFAULT 0,
      tsi REAL
    )
    """)
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_ts ON {table_name}(ts);")
    c.commit()
    c.close()


def insert_history_sample(ts, rms, band, peaks, tremor_f, gsr, batt, qf, tsi):
    table = history_table_for_ts(ts)
    ensure_history_table(table)
    c = connect()
    c.execute(
        f"INSERT OR REPLACE INTO {table}(ts,rms_diff,band_4_6,peaks,tremor_f,gsr,batt,qf,tsi) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (ts, rms, band, peaks, tremor_f, gsr, batt, qf, tsi)
    )
    c.commit()
    c.close()


def insert_event(ts, ev_type, severity=1, meta="", category="system", subtype="", message=""):
    c = connect()
    c.execute(
        "INSERT INTO events(ts,type,severity,meta,category,subtype,message) VALUES (?,?,?,?,?,?,?)",
        (int(ts), str(ev_type), int(severity), str(meta), str(category), str(subtype), str(message))
    )
    c.commit()
    c.close()


def ensure_telemetry_table():
    c = connect()
    cur = c.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS telemetry (
      ts INTEGER PRIMARY KEY,
      rms1 REAL,
      rms2 REAL,
      rms_diff REAL,
      freq REAL,
      band_4_6 REAL,
      peaks REAL,
      bai REAL,
      ci REAL,
      tvi REAL,
      delay_ms REAL,
      neuro REAL,
      acc REAL,
      gyro REAL,
      gsr REAL,
      mode INTEGER,
      m1 INTEGER,
      m2 INTEGER,
      batt REAL,
      qf INTEGER DEFAULT 0
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(ts);")
    c.commit()
    c.close()


def insert_telemetry_sample(
    ts,
    rms1,
    rms2,
    rms_diff,
    freq,
    band_4_6,
    peaks,
    bai,
    ci,
    tvi,
    delay_ms,
    neuro,
    acc,
    gyro,
    gsr,
    mode,
    m1,
    m2,
    batt,
    qf
):
    ensure_telemetry_table()
    c = connect()
    c.execute(
        "INSERT OR REPLACE INTO telemetry("
        "ts,rms1,rms2,rms_diff,freq,band_4_6,peaks,bai,ci,tvi,delay_ms,neuro,acc,gyro,gsr,mode,m1,m2,batt,qf"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            int(ts),
            rms1,
            rms2,
            rms_diff,
            freq,
            band_4_6,
            peaks,
            bai,
            ci,
            tvi,
            delay_ms,
            neuro,
            acc,
            gyro,
            gsr,
            mode,
            m1,
            m2,
            batt,
            qf
        )
    )
    c.commit()
    c.close()
