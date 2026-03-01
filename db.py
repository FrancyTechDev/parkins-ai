import sqlite3
from config import DB_PATH

def connect():
    return sqlite3.connect(DB_PATH)

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
      tsi INTEGER
    )
    """)

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
    CREATE TABLE IF NOT EXISTS daily_agg (
      day TEXT PRIMARY KEY,
      tsi_mean REAL,
      tsi_p90 REAL,
      tremor_minutes REAL,
      sample_count INTEGER,
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
    CREATE TABLE IF NOT EXISTS events (
      ts INTEGER NOT NULL,
      type TEXT NOT NULL,
      severity REAL,
      meta TEXT
    )
    """)

    c.commit()
    c.close()