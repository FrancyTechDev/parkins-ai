import sqlite3
from config import DB_PATH

def connect():
    # timeout per evitare blocchi su Windows
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    # WAL se possibile (su alcuni setup Windows può dare problemi: non deve bloccare)
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
      meta TEXT DEFAULT ""
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);")

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

    c.commit()
    c.close()