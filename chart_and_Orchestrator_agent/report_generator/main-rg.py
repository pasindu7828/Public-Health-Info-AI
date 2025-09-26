import os
import re
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

load_dotenv()

# ---------- Internal services ----------
from .services.nlp import extract as extract_from_text
from .services.visualize import make_line_chart
from .services.summarizer import generate_summary
from .services.render import render_html_report, html_to_pdf_strict
from .services.timeseries import generate_synthetic_timeseries, fetch_covid_timeseries  # <-- import the new helper


# ---------- Paths / Config ----------
ARTIFACTS_ROOT = Path("agents/report_generator/artifacts").resolve()
CHARTS_DIR = str((ARTIFACTS_ROOT / "charts").resolve())
REPORTS_DIR = str((ARTIFACTS_ROOT / "reports").resolve())
CSS_PATH = str(Path("agents/report_generator/static/css/style.css").resolve())
WKHTMLTOPDF = os.getenv(
    "WKHTMLTOPDF",
    r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
)

# Ensure folders exist
(Path(CHARTS_DIR)).mkdir(parents=True, exist_ok=True)
(Path(REPORTS_DIR)).mkdir(parents=True, exist_ok=True)

def slugify(text: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")


# ---------- Schemas ----------
class Source(BaseModel):
    name: str
    url: str
    date: Optional[str] = None

class Insights(BaseModel):
    weekly_increase: Optional[str] = None
    top_region: Optional[str] = None
    anomalies: Optional[List[str]] = None

class ReportRequest(BaseModel):
    disease: str
    region: str
    date_from: str
    date_to: str
    timeseries: Optional[List[dict]] = []
    insights: Optional[Insights] = None
    sources: Optional[List[Source]] = []

class ReportResponse(BaseModel):
    summary: str
    visuals: List[dict]
    report_url: Optional[str] = None
    pdf_url: Optional[str] = None
    disclaimer: str
    sources: List[Source]

class TextRequest(BaseModel):
    query: str


# ---------- App ----------
app = FastAPI(title="Report Generator Agent")

# CORS (Vite on 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve artifacts (charts + reports)
app.mount(
    "/agents/report_generator/artifacts",
    StaticFiles(directory=str(ARTIFACTS_ROOT)),
    name="artifacts",
)

app.mount(
    "/agents/report_generator/static",
    StaticFiles(directory="agents/report_generator/static"),
    name="static",
)

@app.get("/health")
def health_check():
    from datetime import datetime
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ---------- Helpers ----------
def _public_chart_path_or_fix(disease: str, region: str, date_from: str, date_to: str, suggested_public_path: str) -> str:
    """
    Ensure the chart URL we return actually points to a file that exists.
    If the suggested path doesn't exist (e.g., because of a '-from_' slug mismatch),
    try the canonical filename pattern without '-from'.
    """
    charts_fs = Path(CHARTS_DIR)
    artifacts_prefix = "/agents/report_generator/artifacts/charts"

    # 1) If suggested path exists, use it
    basename = Path(suggested_public_path).name
    fs_path = charts_fs / basename
    if fs_path.exists():
        return f"{artifacts_prefix}/{basename}"

    # 2) Try a canonical filename (no '-from_')
    canonical_name = f"{slugify(disease)}_{slugify(region)}_{date_from.replace('-','')}_{date_to.replace('-','')}.png"
    canonical_fs = charts_fs / canonical_name
    if canonical_fs.exists():
        return f"{artifacts_prefix}/{canonical_name}"

    # 3) If nothing found, fall back to dummy
    dummy = charts_fs / "dummy_chart.png"
    if dummy.exists():
        return f"{artifacts_prefix}/dummy_chart.png"

    # 4) Last resort: return the original (may 404, but we tried)
    return suggested_public_path


# ---------- Core endpoints ----------
@app.post("/report", response_model=ReportResponse)
def generate_report(request: ReportRequest):
    # 1) Summary
    summary = generate_summary(
        disease=request.disease,
        region=request.region,
        date_from=request.date_from,
        date_to=request.date_to,
        timeseries=request.timeseries or [],
        insights=request.insights.dict() if request.insights else None,
    )

    # 2) Chart – draw if we have a timeseries
    if request.timeseries:
        # make_line_chart should save into CHARTS_DIR and return a path
        raw_chart_path = make_line_chart(
            timeseries=request.timeseries,
            disease=request.disease,
            region=request.region,
            date_from=request.date_from,
            date_to=request.date_to,
            charts_dir=CHARTS_DIR,
        )
        # Normalize to a public path that actually exists
        chart_public = _public_chart_path_or_fix(
            request.disease, request.region, request.date_from, request.date_to, raw_chart_path
        )
    else:
        chart_public = "/agents/report_generator/artifacts/charts/dummy_chart.png"

    visuals = [{"type": "line", "path": chart_public}]

    # 3) HTML report
    slug = f"{slugify(request.disease)}_{slugify(request.region)}_{request.date_from.replace('-','')}_{request.date_to.replace('-','')}"
    period = f"{request.date_from} to {request.date_to}"

    report_rel_url = render_html_report(
        title=f"{request.disease} — {request.region}",
        period=period,
        summary=summary,
        chart_rel_path=chart_public,   # template uses ../charts/<filename>.png
        sources=[s.dict() for s in (request.sources or [])],
        disclaimer="Auto-generated demo. Verify with official sources.",
        reports_dir=REPORTS_DIR,
        templates_dir="agents/report_generator/templates",
        filename_slug=slug,
    )

    # 4) PDF (inline CSS + absolute chart path)
    report_filename = Path(report_rel_url).name
    html_fs_path = Path(REPORTS_DIR) / report_filename
    pdf_filename = report_filename.replace(".html", ".pdf")
    pdf_fs_path = Path(REPORTS_DIR) / pdf_filename

    # Absolute chart path for wkhtmltopdf
    chart_abs_path = None
    try:
        chart_abs_path = str((Path(CHARTS_DIR) / Path(chart_public).name).resolve())
    except Exception:
        chart_abs_path = None

    pdf_ok = False
    try:
        pdf_ok = html_to_pdf_strict(
            html_path=str(html_fs_path),
            pdf_out_path=str(pdf_fs_path),
            css_abs_path=CSS_PATH,
            chart_abs_path=chart_abs_path,
            wkhtmltopdf_path=WKHTMLTOPDF,
        )
    except Exception:
        pdf_ok = False

    pdf_rel_url = f"/agents/report_generator/artifacts/reports/{pdf_filename}" if pdf_ok else None

    # 5) Response
    return ReportResponse(
        summary=summary,
        visuals=visuals,
        report_url=report_rel_url,
        pdf_url=pdf_rel_url,
        disclaimer=(
            "Auto-generated demo. If timeseries was not provided, the trend chart is illustrative "
            "based on the described change. Verify with official sources."
        ),
        sources=request.sources or [],
    )


from .services.datasources import fetch_timeseries_if_possible

@app.post("/report_from_text", response_model=ReportResponse)
def report_from_text(body: TextRequest):
    if not body.query or len(body.query.strip()) < 8:
        raise HTTPException(status_code=400, detail="Please provide a longer prompt.")

    data = extract_from_text(body.query)

    # Always create/overwrite sources list so we control what appears
    data["sources"] = []

    # Ensure insights dict
    if not isinstance(data.get("insights"), dict):
        data["insights"] = {}

    disease = (data.get("disease") or "").lower()
    real_series = None

    # --- Try real COVID series first (disease.sh / JHU) ---
    if "covid" in disease:
        country = data.get("region") or data.get("country") or "World"
        real_series = fetch_covid_timeseries(country, data["date_from"], data["date_to"])
        if real_series and len(real_series) >= 2:
            data["timeseries"] = real_series

            # compute change from first→last in window (for summary)
            start_val = float(real_series[0].get("value") or 0.0)
            end_val   = float(real_series[-1].get("value") or 0.0)
            pct = 0.0 if start_val == 0 else ((end_val - start_val) / start_val) * 100.0
            data["insights"]["weekly_increase"] = f"{pct:.1f}%"

            # replace any prior sources with the *real* one used
            data["sources"] = [{
                "name": "disease.sh (JHU)",
                "url": "https://disease.sh/docs/#/COVID-19%3A%20JHUCSSE/get_v3_covid_19_historical__country_",
                "date": None
            }]

    # --- If still no series, build an illustrative (synthetic) series and label it clearly ---
    if not data.get("timeseries"):
        # A nicer looking illustrative series (seasonal + mild trend + small noise)
        try:
            from .services.timeseries import generate_illustrative_timeseries
            data["timeseries"] = generate_illustrative_timeseries(
                date_from=data["date_from"],
                date_to=data["date_to"],
                points=24,
                base=100.0,
                trend_pct_total=12.0,   # gentle overall change across the window
                seasonality_amp_pct=8.0,
                noise_pct=2.5,
            )
        except Exception:
            # Fallback to your original simple synthetic series if illustrative helper isn’t available
            data["timeseries"] = generate_synthetic_timeseries(
                date_from=data["date_from"],
                date_to=data["date_to"],
                weekly_increase_str=None,  # don’t force a % if we didn’t parse one
                points=8,
                start_value=100.0,
            )

        # Compute Δ% for the summary (still illustrative)
        ts = data["timeseries"]
        if len(ts) >= 2:
            s = float(ts[0]["value"] or 0.0)
            e = float(ts[-1]["value"] or 0.0)
            pct = 0.0 if s == 0 else ((e - s) / s) * 100.0
            data["insights"]["weekly_increase"] = f"{pct:.1f}%"

        # Mark sources honestly: this is illustrative, plus WHO can be listed as a reference
        data["sources"].append({"name": "Illustrative trend (no official data found)", "url": "about:blank", "date": None})
        data["sources"].append({"name": "WHO (reference)", "url": "https://www.who.int", "date": None})

    # Validate and render
    try:
        req = ReportRequest(**data)
    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=str(ve))

    return generate_report(req)
