# agents/report_generator/services/timeseries.py

from __future__ import annotations
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from urllib.parse import quote
import requests
import math
import random

# ---------- Date helpers ----------
def _parse_date(s: str) -> datetime:
    # Accept YYYY-MM-DD (what your pipeline uses)
    return datetime.strptime(s, "%Y-%m-%d")

def _format_date(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


# ---------- Synthetic series (no default +10%) ----------
def generate_synthetic_timeseries(
    date_from: str,
    date_to: str,
    weekly_increase_str: Optional[str] = None,
    points: int = 8,
    start_value: float = 100.0,
) -> List[dict]:
    """
    Simple illustrative curve with optional weekly % increase.
    Produces a list of {date, value}. If no % is given, the line is flat.
    """
    d0 = _parse_date(date_from)
    d1 = _parse_date(date_to)
    if d1 <= d0:
        d1 = d0 + timedelta(days=7)

    total_days = (d1 - d0).days
    step = max(1, total_days // max(1, points - 1))

    # If a percent is provided, apply it gently across the points.
    # If NOT provided, DO NOT inject defaults → keep it flat (factor = 1.0).
    factor = 1.0
    if weekly_increase_str:
        try:
            pct = float(weekly_increase_str.strip().replace("%", ""))
            # Distribute weekly % roughly over the number of points
            factor = 1.0 + (pct / 100.0) / max(1, (points - 1))
        except Exception:
            # If parsing fails, stay flat instead of faking a trend
            factor = 1.0

    vals = []
    v = float(start_value)
    cur = d0
    for _ in range(points):
        vals.append({"date": _format_date(cur), "value": round(v, 2)})
        v *= factor
        cur = cur + timedelta(days=step)

    # Ensure last point aligns with date_to
    if vals[-1]["date"] != _format_date(d1):
        vals[-1]["date"] = _format_date(d1)

    return vals


# ---------- Real COVID time series (cumulative cases) ----------
def fetch_covid_timeseries(country: str, date_from: str, date_to: str) -> Optional[List[Dict]]:
    """
    Fetch cumulative COVID-19 cases from disease.sh (JHU) for `country`,
    slice them to [date_from, date_to] inclusive, and return:
        [{ "date": "YYYY-MM-DD", "value": <cumulative_cases_float> }, ...]
    Returns None if no meaningful data is available for that window.
    """
    country = (country or "").strip() or "World"

    # Strict matching and URL-encoding help avoid ambiguous names
    url = f"https://disease.sh/v3/covid-19/historical/{quote(country)}?lastdays=all&strict=true"

    try:
        resp = requests.get(url, timeout=25)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    # Some responses come as [ { country:..., timeline:{...} } ]
    if isinstance(data, list) and data:
        data = data[0]

    # Country responses have .timeline; global has different shape at /historical/all (not used here)
    timeline = data.get("timeline") if isinstance(data, dict) else None
    if not timeline or "cases" not in timeline or not isinstance(timeline["cases"], dict):
        return None

    # disease.sh date keys look like "1/22/20" or "01/22/2020"
    cumulative = []
    for k, v in timeline["cases"].items():
        dt = None
        for fmt in ("%m/%d/%y", "%m/%d/%Y"):
            try:
                dt = datetime.strptime(k, fmt)
                break
            except Exception:
                continue
        if dt is None:
            continue
        cumulative.append((dt, float(v or 0.0)))

    if not cumulative:
        return None

    # Sort oldest → newest
    cumulative.sort(key=lambda x: x[0])

    # Slice to requested window
    d0 = _parse_date(date_from)
    d1 = _parse_date(date_to)
    if d1 < d0:
        d0, d1 = d1, d0

    window = [(dt, val) for dt, val in cumulative if d0 <= dt <= d1]
    if not window:
        return None

    # If the entire window is zeros (unlikely for real country windows), treat as no data
    if not any(val > 0 for _, val in window):
        return None

    return [{"date": _format_date(dt), "value": round(val, 2)} for dt, val in window]

def generate_illustrative_timeseries(
    date_from: str,
    date_to: str,
    points: int = 24,
    base: float = 100.0,
    trend_pct_total: float = 15.0,  # +15% over the whole window
    seasonality_amp_pct: float = 10.0,  # ±10% seasonal swing
    noise_pct: float = 3.0,  # ±3% noise
) -> List[dict]:
    """
    Produce a realistic-looking but clearly illustrative series:
    base * trend * (1 + seasonality) + small noise, evenly spaced.
    """
    d0 = _parse_date(date_from)
    d1 = _parse_date(date_to)
    if d1 <= d0:
        d1 = d0 + timedelta(days=7)

    total_days = (d1 - d0).days
    step = max(1, total_days // max(1, points - 1))

    vals = []
    cur = d0

    # trend multiplier from 1.0 → 1+trend over the series
    trend_total = 1.0 + trend_pct_total / 100.0

    for i in range(points):
        t = i / max(1, points - 1)
        trend = 1.0 + (trend_total - 1.0) * t

        # simple seasonal (one full cycle)
        season = seasonality_amp_pct / 100.0 * math.sin(2.0 * math.pi * t)

        # small random noise
        noise = 1.0 + random.uniform(-noise_pct, noise_pct) / 100.0

        v = base * trend * (1.0 + season) * noise
        vals.append({"date": _format_date(cur), "value": round(v, 2)})
        cur = cur + timedelta(days=step)

    if vals[-1]["date"] != _format_date(d1):
        vals[-1]["date"] = _format_date(d1)

    return vals