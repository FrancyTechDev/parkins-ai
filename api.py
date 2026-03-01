import os
import time
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from db import init_db, connect
from demo_seed import seed_demo
from baseline import recompute_baseline
from aggregate import recompute_daily, recompute_weekly, recompute_monthly
from forecast import forecast_72h
from prognosis import course_outlook, time_to_threshold, symptoms_outlook
from report_pdf import generate_report_pdf
from config import TSI_SEVERE

app = FastAPI()
templates = Jinja2Templates(directory="templates")


init_db()

if os.getenv("DEMO_MODE") == "1":
    seed_demo(days=7, step_sec=10)


REPORT_PATH = "/tmp/report.pdf" if os.getenv("RENDER") else "report.pdf"


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/state")
def state():
    c = connect()
    df = pd.read_sql("SELECT * FROM samples_ref ORDER BY ts DESC LIMIT 1", c)
    c.close()
    if df.empty:
        return {"current": None, "message": "No data yet"}
    return {"current": df.iloc[0].to_dict()}


@app.post("/api/feedback")
def feedback(day: str, score: int, note: str = ""):
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


@app.post("/api/agg")
def recompute_all():
    recompute_baseline()
    recompute_daily(7)
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


@app.get("/api/report/pdf")
def report_pdf_generate():
    generate_report_pdf(REPORT_PATH)
    return {"ok": True, "file": "report.pdf"}


@app.get("/download/report.pdf")
def download_report_pdf():
    return FileResponse(REPORT_PATH, media_type="application/pdf", filename="report.pdf")

@app.get("/ping")
def ping():
    return {"pong": True, "module": "api.py"}

@app.post("/api/event")
def log_event(ts: int, type: str, severity: int = 1, meta: str = ""):
    if type not in ("fall", "near_fall", "freeze", "sos"):
        return {"ok": False, "error": "type must be fall|near_fall|freeze|sos"}
    if severity < 1 or severity > 3:
        return {"ok": False, "error": "severity must be 1..3"}

    c = connect()
    c.execute(
        "INSERT INTO events(ts,type,severity,meta) VALUES (?,?,?,?)",
        (ts, type, severity, meta)
    )
    c.commit()
    c.close()
    return {"ok": True}

