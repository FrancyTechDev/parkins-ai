import numpy as np
import pandas as pd
from db import connect
from config import TSI_SEVERE, TSI_HIGH

# -------------------------
# Helpers
# -------------------------
def _load_daily(limit: int = 60) -> pd.DataFrame:
    """
    Carica le aggregazioni giornaliere.
    Richiede che daily_agg sia già popolata (recompute_daily).
    """
    c = connect()
    df = pd.read_sql(
        "SELECT day, tsi_mean, tsi_p90, tremor_minutes, sample_count "
        "FROM daily_agg ORDER BY day ASC",
        c
    )
    c.close()

    if df.empty:
        return df

    if len(df) > limit:
        df = df.iloc[-limit:].copy()
    return df


def _trend(y: np.ndarray):
    """
    Trend lineare y = m*x + b e stima volatilità sui residui.
    """
    x = np.arange(len(y), dtype=float)
    m, b = np.polyfit(x, y, 1)
    resid = y - (m * x + b)
    sigma = float(np.std(resid)) if len(resid) > 2 else float(np.std(y))
    return float(m), float(b), sigma


def _confidence(n_days: int) -> str:
    """
    Confidenza basata SOLO sul numero di giorni (semplice e onesta).
    """
    if n_days >= 30:
        return "alta"
    if n_days >= 14:
        return "media"
    if n_days >= 7:
        return "bassa"
    return "molto_bassa"


# -------------------------
# Core outputs
# -------------------------
def course_outlook():
    """
    Risponde a: "Quale sarà l’andamento futuro?"
    Interpretazione corretta: andamento dell’indice TSI.
    """
    df = _load_daily()
    if df.empty or len(df) < 5:
        return {
            "status": "insufficient_data",
            "message": "Servono almeno 5 giorni in daily_agg."
        }

    y = df["tsi_mean"].to_numpy(dtype=float)
    m, b, sigma = _trend(y)

    if abs(m) < 0.05:
        label = "stabile"
    elif m > 0:
        label = "in peggioramento"
    else:
        label = "in miglioramento"

    return {
        "status": "ok",
        "days_used": int(len(df)),
        "confidence": _confidence(len(df)),
        "trend_tsi_per_day": m,
        "volatility": sigma,
        "course": label,
        "current_tsi": float(y[-1]),
        "start_tsi": float(y[0]),
    }


def time_to_threshold(threshold: float):
    """
    Risponde a: "Tra quanto diventerà grave?"
    Interpretazione corretta: tempo stimato a superare una soglia del TSI (es. TSI_SEVERE).
    Restituisce range (grezzo) usando la volatilità dei residui.
    """
    df = _load_daily()
    if df.empty or len(df) < 5:
        return {"status": "insufficient_data"}

    y = df["tsi_mean"].to_numpy(dtype=float)
    m, b, sigma = _trend(y)
    current = float(y[-1])

    # se trend non cresce, non ha senso stimare tempo a soglia
    if m <= 0:
        return {
            "status": "ok",
            "reachable": False,
            "reason": "trend_non_crescente",
            "threshold": float(threshold),
            "current_tsi": current,
            "trend_tsi_per_day": m,
            "confidence": _confidence(len(df))
        }

    days_est = (threshold - current) / m

    # range grezzo: incertezza sul livello attuale usando sigma
    lo = (threshold - (current + sigma)) / m
    hi = (threshold - (current - sigma)) / m

    lo = float(max(0.0, lo))
    hi = float(max(0.0, hi))
    days_est = float(days_est)

    return {
        "status": "ok",
        "reachable": True,
        "threshold": float(threshold),
        "current_tsi": current,
        "trend_tsi_per_day": m,
        "days_est": days_est,
        "days_range": [lo, hi],
        "confidence": _confidence(len(df))
    }


def symptoms_outlook():
    """
    Risponde a: "Quali sintomi ci saranno?"
    SOLO ciò che è supportabile dai tuoi segnali:
      - tremore (dal TSI)
    (Instabilità/cadute solo se aggiungi eventi specifici in tabella events.)
    """
    df = _load_daily()
    if df.empty or len(df) < 3:
        return {"status": "insufficient_data"}

    last = float(df["tsi_mean"].to_numpy(dtype=float)[-1])
    conf = _confidence(len(df))

    if last >= TSI_SEVERE:
        return {
            "status": "ok",
            "likely": "tremore_persistente_e_limitante",
            "confidence": conf,
            "tsi": last
        }
    if last >= TSI_HIGH:
        return {
            "status": "ok",
            "likely": "aumento_episodi_tremore",
            "confidence": conf,
            "tsi": last
        }
    return {
        "status": "ok",
        "likely": "tremore_moderato_o_stabile",
        "confidence": conf,
        "tsi": last
    }


def full_prognosis():
    """
    Output unico, utile per report: include le 4 domande essenziali.
    """
    course = course_outlook()
    t_severe = time_to_threshold(TSI_SEVERE)
    symp = symptoms_outlook()

    # "tra quanto peggioreranno i sintomi?" -> legato al trend e alle soglie
    if course.get("status") != "ok":
        worsen = {
            "status": "insufficient_data",
            "message": "Dati insufficienti per stimare trend/peggioramento."
        }
    else:
        m = course["trend_tsi_per_day"]
        if m > 0.05:
            worsen = {
                "status": "ok",
                "statement": "Peggioramento plausibile nel periodo osservato (trend positivo).",
                "trend_tsi_per_day": m,
                "confidence": course["confidence"]
            }
        else:
            worsen = {
                "status": "ok",
                "statement": "Nessun peggioramento significativo stimato nel breve (trend ~0 o negativo).",
                "trend_tsi_per_day": m,
                "confidence": course["confidence"]
            }

    return {
        "course": course,
        "time_to_severe": t_severe,
        "worsening": worsen,
        "symptoms_outlook": symp
    }