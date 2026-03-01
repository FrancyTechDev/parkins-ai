import time
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from db import connect
from forecast import forecast_72h
from config import TSI_HIGH, TSI_SEVERE
from prognosis import course_outlook, time_to_threshold, symptoms_outlook

EDU_SUMMARY = (
    "Il morbo di Parkinson è una patologia neurodegenerativa progressiva. "
    "I sintomi motori principali includono tremore, rigidità, bradicinesia e instabilità posturale. "
    "L’andamento è variabile tra individui. Questo report usa biomarcatori digitali (IMU/GSR) per monitoraggio e trend: "
    "non sostituisce diagnosi o valutazione clinica."
)

def _df_table(df: pd.DataFrame, max_rows=12):
    if df is None or df.empty:
        return None
    d = df.copy()
    if len(d) > max_rows:
        d = d.tail(max_rows)
    data = [list(d.columns)] + d.astype(str).values.tolist()
    t = Table(data, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.black),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey]),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    return t

def generate_report_pdf(path="report.pdf"):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(path)

    c = connect()
    profile = pd.read_sql("SELECT key, value FROM user_profile ORDER BY key", c)
    daily = pd.read_sql("SELECT day, tsi_mean, tsi_p90, tremor_minutes, sample_count FROM daily_agg ORDER BY day ASC", c)
    weekly = pd.read_sql("SELECT week, tsi_mean, tsi_trend, high_days FROM weekly_agg ORDER BY week ASC", c)
    monthly = pd.read_sql("SELECT month, tsi_mean, tsi_trend FROM monthly_agg ORDER BY month ASC", c)
    fb = pd.read_sql("SELECT day, score, note FROM user_feedback ORDER BY day ASC", c)
    c.close()

    fc = forecast_72h()
    course = course_outlook()
    t_severe = time_to_threshold(TSI_SEVERE)
    symp = symptoms_outlook()

    elems = []
    elems.append(Paragraph("PARKINS-AI — Report personalizzato", styles["Title"]))
    elems.append(Spacer(1, 10))
    elems.append(Paragraph(time.strftime("Generato: %Y-%m-%d %H:%M:%S"), styles["Normal"]))
    elems.append(Spacer(1, 16))

    # PROFILO
    elems.append(Paragraph("1) Parametri della persona (profilo)", styles["Heading2"]))
    pt = _df_table(profile.rename(columns={"key":"Parametro","value":"Valore"}))
    elems.append(pt if pt else Paragraph("Profilo non compilato.", styles["Normal"]))
    elems.append(Spacer(1, 14))

    # SINTESI NUMERICA
    elems.append(Paragraph("2) Sintesi dei dati (dati digitali)", styles["Heading2"]))
    if not daily.empty:
        last = daily.iloc[-1]
        elems.append(Paragraph(
            f"Ultimo giorno: TSI medio={float(last.tsi_mean):.2f} | p90={float(last.tsi_p90):.2f} | minuti tremore (stima)={float(last.tremor_minutes):.1f}",
            styles["Normal"]
        ))
    else:
        elems.append(Paragraph("Dati daily_agg non disponibili.", styles["Normal"]))
    elems.append(Spacer(1, 10))

    # TABELLE AGGREGATE
    elems.append(Paragraph("3) Medie giornaliere", styles["Heading3"]))
    dt = _df_table(daily.rename(columns={"day":"Giorno","tsi_mean":"TSI medio","tsi_p90":"TSI p90","tremor_minutes":"Min tremore","sample_count":"Campioni"}))
    elems.append(dt if dt else Paragraph("Nessuna media giornaliera.", styles["Normal"]))
    elems.append(Spacer(1, 10))

    elems.append(Paragraph("4) Medie settimanali", styles["Heading3"]))
    wt = _df_table(weekly.rename(columns={"week":"Settimana","tsi_mean":"TSI medio","tsi_trend":"Trend","high_days":"Giorni alti"}))
    elems.append(wt if wt else Paragraph("Nessuna media settimanale.", styles["Normal"]))
    elems.append(Spacer(1, 10))

    elems.append(Paragraph("5) Medie mensili", styles["Heading3"]))
    mt = _df_table(monthly.rename(columns={"month":"Mese","tsi_mean":"TSI medio","tsi_trend":"Trend"}))
    elems.append(mt if mt else Paragraph("Nessuna media mensile.", styles["Normal"]))
    elems.append(Spacer(1, 14))

    # FEEDBACK
    elems.append(Paragraph("6) Feedback soggettivo (1–5)", styles["Heading2"]))
    fbt = _df_table(fb.rename(columns={"day":"Giorno","score":"Score","note":"Nota"}))
    elems.append(fbt if fbt else Paragraph("Nessun feedback inserito.", styles["Normal"]))
    elems.append(Spacer(1, 14))

    # FORECAST
    elems.append(Paragraph("7) Previsioni (72 ore)", styles["Heading2"]))
    if fc:
        elems.append(Paragraph(
            f"Previsione TSI tra 72h: {fc['pred']:.2f} (intervallo ~80%: {fc['lo']:.2f} – {fc['hi']:.2f}), ore usate: {fc.get('hours_used','?')}.",
            styles["Normal"]
        ))
    else:
        elems.append(Paragraph("Forecast non disponibile (dati insufficienti).", styles["Normal"]))
    elems.append(Spacer(1, 14))

    # PROGNOSI (le tue domande)
    elems.append(Paragraph("8) Prognosi e risposte alle domande essenziali (basata su TSI)", styles["Heading2"]))

    # Q1 andamento futuro
    if course.get("status") == "ok":
        elems.append(Paragraph(
            f"Q1) Quale sarà l’andamento futuro? → {course['course']} (trend {course['trend_tsi_per_day']:.3f} TSI/giorno, confidenza {course['confidence']}).",
            styles["Normal"]
        ))
    else:
        elems.append(Paragraph("Q1) Andamento futuro → dati insufficienti.", styles["Normal"]))

    # Q2 quando grave
    if t_severe and t_severe.get("reachable"):
        lo, hi = t_severe["days_range"]
        elems.append(Paragraph(
            f"Q2) Tra quanto diventerà grave? → superamento soglia TSI={TSI_SEVERE}: stima {t_severe['days_est']:.1f} giorni (range {lo:.1f}–{hi:.1f}).",
            styles["Normal"]
        ))
    elif t_severe and t_severe.get("reachable") is False:
        elems.append(Paragraph(
            "Q2) Tra quanto diventerà grave? → non stimabile perché il trend non è crescente (nessuna evidenza di peggioramento nel periodo analizzato).",
            styles["Normal"]
        ))
    else:
        elems.append(Paragraph("Q2) Tra quanto diventerà grave? → dati insufficienti.", styles["Normal"]))

    # Q3 peggioramento sintomi
    if course.get("status") == "ok":
        if course["trend_tsi_per_day"] > 0.05:
            elems.append(Paragraph(
                "Q3) Tra quanto i sintomi peggioreranno? → tendenza al peggioramento già presente (trend positivo). Il tempo dipende dal superamento soglie TSI.",
                styles["Normal"]
            ))
        else:
            elems.append(Paragraph(
                "Q3) Tra quanto i sintomi peggioreranno? → non previsto peggioramento significativo nel breve in base al trend stimato.",
                styles["Normal"]
            ))
    else:
        elems.append(Paragraph("Q3) Peggioramento sintomi → dati insufficienti.", styles["Normal"]))

    # Q4 quali sintomi
    elems.append(Paragraph(
        f"Q4) Quali sintomi ci saranno? → {symp.get('likely','non stimabile')} (confidenza {symp.get('confidence','bassa')}).",
        styles["Normal"]
    ))

    elems.append(Spacer(1, 12))
    elems.append(Paragraph(
        "Nota: le stime sono basate su un indice digitale (TSI) derivato da IMU/GSR. Non è una scala clinica ufficiale. "
        "Usare come supporto al monitoraggio.",
        styles["Italic"]
    ))
    elems.append(Spacer(1, 16))

    # EDU
    elems.append(Paragraph("9) Riassunto della malattia (educazionale)", styles["Heading2"]))
    elems.append(Paragraph(EDU_SUMMARY, styles["Normal"]))

    doc.build(elems)
    return path