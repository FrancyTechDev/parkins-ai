import os
import time
import csv
import io
import pandas as pd
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
import ctypes

from db import init_db, connect, get_setting, set_setting, history_table_for_ts, ensure_history_table
from demo_seed import seed_demo
from baseline import recompute_baseline
from aggregate import recompute_daily, recompute_weekly, recompute_monthly
from forecast import forecast_72h
from prognosis import course_outlook, time_to_threshold, symptoms_outlook
from progression import full_progression
from report_pdf import generate_report_pdf
from config import TSI_SEVERE

app = FastAPI()
templates = Jinja2Templates(directory="templates")

init_db()

# DEMO seed disabilitato: evitare dati simulati in DB

REPORT_PATH = "/tmp/report.pdf" if os.getenv("RENDER") else "report.pdf"

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "page": "overview"})

@app.get("/series", response_class=HTMLResponse)
def series_page(request: Request):
    return templates.TemplateResponse("series.html", {"request": request, "page": "series"})

@app.get("/tremor", response_class=HTMLResponse)
def tremor_page(request: Request):
    return templates.TemplateResponse("tremor.html", {"request": request, "page": "tremor"})

@app.get("/events", response_class=HTMLResponse)
def events_page(request: Request):
    return templates.TemplateResponse("events.html", {"request": request, "page": "events"})

@app.get("/feedback", response_class=HTMLResponse)
def feedback_page(request: Request):
    return templates.TemplateResponse("feedback.html", {"request": request, "page": "feedback"})

@app.get("/progression", response_class=HTMLResponse)
def progression_page(request: Request):
    return templates.TemplateResponse("progression.html", {"request": request, "page": "progression"})

@app.get("/forecasts", response_class=HTMLResponse)
def forecasts_page(request: Request):
    return templates.TemplateResponse("forecasts.html", {"request": request, "page": "forecasts"})

@app.get("/aggregations", response_class=HTMLResponse)
def aggregations_page(request: Request):
    return templates.TemplateResponse("aggregations.html", {"request": request, "page": "aggregations"})

@app.get("/export", response_class=HTMLResponse)
def export_page(request: Request):
    return templates.TemplateResponse("export.html", {"request": request, "page": "export"})

@app.get("/report", response_class=HTMLResponse)
def report_page(request: Request):
    return templates.TemplateResponse("report.html", {"request": request, "page": "report"})

@app.get("/debug", response_class=HTMLResponse)
def debug_page(request: Request):
    return templates.TemplateResponse("debug.html", {"request": request, "page": "debug"})

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request, "page": "settings"})

@app.get("/ping")
def ping():
    return {"pong": True, "module": "api.py"}

@app.get("/api/state")
def state():
    c = connect()
    df = pd.read_sql("SELECT * FROM samples_ref ORDER BY ts DESC LIMIT 1", c)
    c.close()
    if df.empty:
        return {"current": None, "message": "No data yet"}
    return {"current": df.iloc[0].to_dict()}

@app.get("/api/settings")
def api_settings():
    return {"ingest_mode": get_setting("ingest_mode", "on")}

@app.post("/api/settings")
async def api_settings_set(request: Request, mode: str = None):
    if mode is None:
        try:
            payload = await request.json()
            mode = payload.get("mode", mode)
        except Exception:
            pass
    if mode not in ("on", "off", "auto"):
        return {"ok": False, "error": "mode must be on|off|auto"}
    set_setting("ingest_mode", mode)
    # Log as system event
    c = connect()
    c.execute(
        "INSERT INTO events(ts,type,severity,meta,category,subtype,message) VALUES (?,?,?,?,?,?,?)",
        (int(time.time()), "setting", 1, f"ingest_mode={mode}", "system", "ingest_mode", "Cambio modalita salvataggio")
    )
    c.commit()
    c.close()
    return {"ok": True, "ingest_mode": mode}

@app.post("/api/feedback")
async def feedback(request: Request, day: str = None, score: int = None, note: str = ""):
    # Support JSON body or query params without requiring python-multipart
    if day is None or score is None:
        try:
            payload = await request.json()
            day = payload.get("day", day)
            score = payload.get("score", score)
            note = payload.get("note", note)
        except Exception:
            pass

    if day is None or score is None:
        return {"ok": False, "error": "day and score required"}

    try:
        score = int(score)
    except Exception:
        return {"ok": False, "error": "score must be integer 1..5"}

    if score < 1 or score > 5:
        return {"ok": False, "error": "score must be 1..5"}

    c = connect()
    c.execute(
        "INSERT OR REPLACE INTO user_feedback(day,score,note,created_ts) VALUES (?,?,?,?)",
        (day, score, note, int(time.time()))
    )
    c.commit()
    c.close()
    return {"ok": True}

@app.post("/api/event")
def log_event(ts: int, type: str, severity: int = 1, meta: str = ""):
    if type not in ("fall", "near_fall", "freeze", "sos"):
        return {"ok": False, "error": "type must be fall|near_fall|freeze|sos"}
    if severity < 1 or severity > 3:
        return {"ok": False, "error": "severity must be 1..3"}

    c = connect()
    c.execute("INSERT INTO events(ts,type,severity,meta) VALUES (?,?,?,?)", (ts, type, severity, meta))
    c.commit()
    c.close()
    return {"ok": True}

@app.post("/api/system_event")
def log_system_event(
    ts: int = None,
    category: str = "system",
    type: str = "generic",
    subtype: str = "",
    severity: int = 1,
    message: str = "",
    meta: str = ""
):
    ts = int(ts) if ts is not None else int(time.time())
    c = connect()
    c.execute(
        "INSERT INTO events(ts,type,severity,meta,category,subtype,message) VALUES (?,?,?,?,?,?,?)",
        (ts, type, severity, meta, category, subtype, message)
    )
    c.commit()
    c.close()
    return {"ok": True}

@app.get("/api/history/ensure")
def ensure_history(day: str):
    # day format: YYYY-MM-DD
    try:
        dt = datetime.strptime(day, "%Y-%m-%d")
    except Exception:
        return {"ok": False, "error": "day must be YYYY-MM-DD"}
    table = f"history_{dt.strftime('%Y_%m_%d')}"
    ensure_history_table(table)
    return {"ok": True, "table": table}

@app.post("/api/agg")
def recompute_all():
    recompute_baseline()
    recompute_daily(14)
    recompute_weekly()
    recompute_monthly()
    return {"ok": True}

@app.get("/api/forecast")
def get_forecast():
    return forecast_72h()

@app.get("/api/prognosis")
def get_prognosis():
    return {
        "course": course_outlook(),
        "time_to_severe": time_to_threshold(TSI_SEVERE),
        "symptoms_outlook": symptoms_outlook()
    }

@app.get("/api/progression")
def get_progression():
    return full_progression()

@app.get("/api/report/pdf")
def report_pdf_generate():
    generate_report_pdf(REPORT_PATH)
    return {"ok": True, "file": "report.pdf"}

@app.get("/download/report.pdf")
def download_report_pdf():
    return FileResponse(REPORT_PATH, media_type="application/pdf", filename="report.pdf")

# ---- Series APIs (per grafici) ----
@app.get("/api/series/samples")
def series_samples(days: int = 7, limit: int = 5000):
    since_ts = int(time.time()) - int(days) * 86400
    c = connect()
    df = pd.read_sql(
        "SELECT ts, tsi, tremor_f, rms_diff, rms2, band_4_6, peaks, gsr, batt, qf "
        "FROM samples_ref WHERE ts >= ? ORDER BY ts ASC LIMIT ?",
        c, params=(since_ts, limit)
    )
    c.close()
    return {"status": "ok", "rows": df.to_dict(orient="records")}

@app.get("/api/series/daily")
def series_daily(days: int = 90):
    since_day = (datetime.utcnow().date() - timedelta(days=int(days))).isoformat()
    c = connect()
    df = pd.read_sql(
        "SELECT day, tsi_mean, tsi_p90, tremor_minutes, sample_count, "
        "falls, near_falls, freezes, sos, dpi "
        "FROM daily_agg WHERE day >= ? ORDER BY day ASC",
        c, params=(since_day,)
    )
    c.close()
    return {"status": "ok", "rows": df.to_dict(orient="records")}

@app.get("/api/series/weekly")
def series_weekly(weeks: int = 52):
    since_ts = int(time.time()) - int(weeks) * 7 * 86400
    c = connect()
    df = pd.read_sql(
        "SELECT week, tsi_mean, tsi_trend, high_days, updated_ts "
        "FROM weekly_agg WHERE updated_ts >= ? ORDER BY week ASC",
        c, params=(since_ts,)
    )
    c.close()
    return {"status": "ok", "rows": df.to_dict(orient="records")}

@app.get("/api/series/monthly")
def series_monthly(months: int = 24):
    since_ts = int(time.time()) - int(months) * 30 * 86400
    c = connect()
    df = pd.read_sql(
        "SELECT month, tsi_mean, tsi_trend, updated_ts "
        "FROM monthly_agg WHERE updated_ts >= ? ORDER BY month ASC",
        c, params=(since_ts,)
    )
    c.close()
    return {"status": "ok", "rows": df.to_dict(orient="records")}

@app.get("/api/series/events")
def series_events(days: int = 90):
    since_ts = int(time.time()) - int(days) * 86400
    c = connect()
    df = pd.read_sql(
        "SELECT ts, type, severity, meta FROM events WHERE ts >= ? ORDER BY ts ASC",
        c, params=(since_ts,)
    )
    c.close()
    return {"status": "ok", "rows": df.to_dict(orient="records")}

@app.get("/api/series/forecasts")
def series_forecasts(days: int = 30):
    since_ts = int(time.time()) - int(days) * 86400
    c = connect()
    df = pd.read_sql(
        "SELECT created_ts, horizon_h, pred, lo, hi, method "
        "FROM forecasts WHERE created_ts >= ? ORDER BY created_ts ASC",
        c, params=(since_ts,)
    )
    c.close()
    return {"status": "ok", "rows": df.to_dict(orient="records")}

@app.get("/api/series/feedback")
def series_feedback(days: int = 365):
    since_day = (datetime.utcnow().date() - timedelta(days=int(days))).isoformat()
    c = connect()
    df = pd.read_sql(
        "SELECT day, score, note FROM user_feedback WHERE day >= ? ORDER BY day ASC",
        c, params=(since_day,)
    )
    c.close()
    return {"status": "ok", "rows": df.to_dict(orient="records")}

# ---- CSV Export ----
TABLES = {
    "samples_ref": {"ts_col": "ts", "type": "ts"},
    "events": {"ts_col": "ts", "type": "ts"},
    "forecasts": {"ts_col": "created_ts", "type": "ts"},
    "daily_agg": {"ts_col": "day", "type": "day"},
    "weekly_agg": {"ts_col": "updated_ts", "type": "ts"},
    "monthly_agg": {"ts_col": "updated_ts", "type": "ts"},
    "user_feedback": {"ts_col": "day", "type": "day"},
    "baseline": {"ts_col": "updated_ts", "type": "ts"},
    "user_profile": {"ts_col": "updated_ts", "type": "ts"},
}

def list_usb_devices():
    devices = []
    if os.name == "nt":
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if bitmask & (1 << i):
                    drive = f"{chr(65+i)}:\\"
                    dtype = ctypes.windll.kernel32.GetDriveTypeW(drive)
                    # 2 = DRIVE_REMOVABLE
                    if dtype == 2:
                        devices.append({"label": "USB", "path": drive})
        except Exception:
            pass
    else:
        # Prefer real mount points from /proc/mounts (Raspberry/Linux)
        try:
            with open("/proc/mounts", "r", encoding="utf-8") as f:
                mounts = f.readlines()
            for line in mounts:
                parts = line.split()
                if len(parts) < 2:
                    continue
                dev, mnt = parts[0], parts[1]
                if not dev.startswith("/dev/"):
                    continue
                if not (dev.startswith("/dev/sd") or dev.startswith("/dev/mmcblk")):
                    continue
                if not (mnt.startswith("/media/") or mnt.startswith("/mnt/") or mnt.startswith("/run/media/")):
                    continue
                label = os.path.basename(mnt.rstrip("/")) or mnt
                devices.append({"label": label, "path": mnt})
        except Exception:
            pass
        # Fallback scan common mount folders
        if not devices:
            bases = ["/media", "/mnt", "/run/media"]
            for base in bases:
                if not os.path.isdir(base):
                    continue
                for name in os.listdir(base):
                    path = os.path.join(base, name)
                    if not os.path.isdir(path):
                        continue
                    # /media/<user>/<label>
                    if base == "/media":
                        for sub in os.listdir(path):
                            sub_path = os.path.join(path, sub)
                            if os.path.isdir(sub_path):
                                devices.append({"label": sub, "path": sub_path})
                    else:
                        devices.append({"label": name, "path": path})
    return devices

@app.get("/api/usb")
def api_usb_devices():
    return {"ok": True, "devices": list_usb_devices()}

@app.get("/api/export")
def export_csv(table: str, range: str = "week"):
    if table not in TABLES:
        return {"ok": False, "error": "invalid table"}
    days = {"week": 7, "month": 30, "year": 365}.get(range, 7)

    cfg = TABLES[table]
    c = connect()
    cur = c.cursor()

    if cfg["type"] == "ts":
        since_ts = int(time.time()) - days * 86400
        cur.execute(f"SELECT * FROM {table} WHERE {cfg['ts_col']} >= ? ORDER BY {cfg['ts_col']} ASC", (since_ts,))
    else:
        since_day = (datetime.utcnow().date() - timedelta(days=days)).isoformat()
        cur.execute(f"SELECT * FROM {table} WHERE {cfg['ts_col']} >= ? ORDER BY {cfg['ts_col']} ASC", (since_day,))

    rows = cur.fetchall()
    headers = [d[0] for d in cur.description] if cur.description else []
    c.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    content = buf.getvalue()

    filename = f"{table}_{range}.csv"
    return Response(content, media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.get("/api/export_to_device")
def export_csv_to_device(mount: str, table: str, range: str = "week"):
    if table not in TABLES:
        return {"ok": False, "error": "invalid table"}
    devices = [d["path"] for d in list_usb_devices()]
    if mount not in devices:
        return {"ok": False, "error": "device not available"}

    days = {"week": 7, "month": 30, "year": 365}.get(range, 7)
    cfg = TABLES[table]
    c = connect()
    cur = c.cursor()

    if cfg["type"] == "ts":
        since_ts = int(time.time()) - days * 86400
        cur.execute(f"SELECT * FROM {table} WHERE {cfg['ts_col']} >= ? ORDER BY {cfg['ts_col']} ASC", (since_ts,))
    else:
        since_day = (datetime.utcnow().date() - timedelta(days=days)).isoformat()
        cur.execute(f"SELECT * FROM {table} WHERE {cfg['ts_col']} >= ? ORDER BY {cfg['ts_col']} ASC", (since_day,))

    rows = cur.fetchall()
    headers = [d[0] for d in cur.description] if cur.description else []
    c.close()

    filename = f"{table}_{range}.csv"
    out_path = os.path.join(mount, filename)
    try:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "filename": filename, "path": out_path}
