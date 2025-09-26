# backend/orchestrator/main.py

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import re
import os
from typing import Optional, Dict, Any

from .config import AGENTS  # must define at least: {"report": "...", "retrieval": "..."} (chat optional)

# -------------------------
# App & CORS
# -------------------------
app = FastAPI(title="Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REPORT_BASE = AGENTS["report"].rstrip("/")
RETRIEVAL_BASE = AGENTS["retrieval"].rstrip("/")
SEC_BASE = AGENTS.get("security", "").rstrip("/")

# Security creds (env-configurable; defaults are fine for demo)
SEC_USER = os.getenv("SEC_USER", "admin")
SEC_PASS = os.getenv("SEC_PASS", "admin")

# -------------------------
# Schemas
# -------------------------
class TextRequest(BaseModel):
    query: str

class RetrievalRequest(BaseModel):
    question: str

class ChatBody(BaseModel):
    message: str
    history: list[dict] = []  # optional, unused right now

class SearchBody(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = None  # e.g., {"country":"...", "topic":"..."}


# --- Curated suggestions for health queries (prefix → canonical disease) ---
DISEASES = {
    "covid 19": ["covid 19", "covid19", "covid-19", "covid", "corona"],
    "dengue":   ["dengue", "den", "dengu"],
    "influenza": ["influenza", "flu", "flu "],  # note: "flu " to avoid matching words like "fluent"
    "malaria":  ["malaria", "malar"],
    "tuberculosis": ["tuberculosis", "tb", "tuber"],
}

# Put your priority countries first; “World” at the end is nice to have
COUNTRIES = [
    "Sri Lanka", "India", "Bangladesh", "Pakistan", "Nepal",
    "United States", "United Kingdom", "Australia", "Canada",
    "Japan", "China", "France", "Germany", "Spain", "Italy",
    "Indonesia", "World",
]

def _canonical_disease_from_prefix(q: str) -> str | None:
    s = (q or "").lower().strip()
    # strongest signal: user starts typing the disease name
    for canonical, aliases in DISEASES.items():
        for a in aliases:
            if s.startswith(a):
                return canonical
    # weaker: disease occurs anywhere early in the string
    for canonical, aliases in DISEASES.items():
        for a in aliases:
            if a in s:
                return canonical
    return None

def _curated_suggestions(q: str, max_items: int = 10) -> list[str]:
    """
    Returns a list of '<disease> in <country>' suggestions if user is typing a known disease.
    We deliberately avoid metrics like 'deaths', 'cases', etc. per your requirement.
    """
    s = (q or "").strip().lower()
    if not s:
        return []

    disease = _canonical_disease_from_prefix(s)
    if not disease:
        return []

    # Generate the pattern list and filter to the user's current prefix
    raw = []
    for c in COUNTRIES:
        raw.append(f"{disease} in {c}")

        # For COVID we also allow a shorter "covid in X" variant that users often type.
        if disease == "covid 19":
            raw.append(f"covid in {c}")

    # Prefix filter: show only suggestions that begin with what the user typed
    seen = set()
    out = []
    for item in raw:
        if item.lower().startswith(s) and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
        if len(out) >= max_items:
            break
    return out


# -------------------------
# Health
# -------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


# -------------------------
# Report routes (pass-through)
# -------------------------
@app.post("/route/report_from_text")
async def route_report_from_text(body: TextRequest):
    url = f"{REPORT_BASE}/report_from_text"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=body.dict())
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@app.post("/route/report")
async def route_report(req: Request):
    try:
        payload = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    url = f"{REPORT_BASE}/report"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=payload)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


# -------------------------
# Static artifact proxy (charts, html, pdfs) from Report Agent
# -------------------------
@app.api_route("/agents/{path:path}", methods=["GET"])
async def proxy_agents(path: str, request: Request):
    upstream = f"{REPORT_BASE}/agents/{path}"

    headers = {}
    for k, v in request.headers.items():
        if k.lower() in {"range", "accept", "accept-encoding", "user-agent"}:
            headers[k] = v

    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.get(upstream, headers=headers)
    return Response(
        content=r.content,
        status_code=r.status_code,
        headers={"content-type": r.headers.get("content-type", "application/octet-stream")},
    )


# -------------------------
# Retrieval pass-through (direct call)
# -------------------------
@app.post("/route/retrieval/search")
async def route_retrieval_search(body: RetrievalRequest):
    url = f"{RETRIEVAL_BASE}/search"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=body.dict())
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


# -------------------------
# CHAT ROUTER
#   - Real-world data intent -> Retrieval Agent (/search)
#   - Report/graph intent     -> Report Agent (/report_from_text)
#   - Otherwise               -> canned Chat Agent reply
# -------------------------

# Explicit phrases that mean "make me a report/graph"
REPORT_KEY_PHRASES = [
    "report", "graph", "chart", "figure", "pdf",
    "generate a report", "create a report", "visualize", "visualise",
]

# Disease hints used with "trend/time series" to qualify a reporting intent
REPORT_DISEASE_HINTS = [
    "dengue", "malaria", "covid", "influenza", "flu", "tb", "tuberculosis",
]

# Retrieval keywords: things we have adapters/APIs for or general metrics
RETRIEVAL_KWS = [
    # Flu/ILI
    "flu", "influenza", "ili",
    # COVID & general epi terms
    "covid", "cases", "deaths", "recovered", "incidence", "prevalence",
    "mortality", "death rate", "case fatality",
    # medicines / fda
    "side effect", "adverse", "reaction", "fda", "medicine", "drug",
    # nutrition / usda
    "nutrition", "usda", "vitamin", "protein", "calcium", "iron",
    # world bank topics
    "life expectancy", "under 5 mortality", "under-5 mortality", "under five mortality",
    "health expenditure", "health spending", "malaria incidence", "tb incidence", "tuberculosis incidence",
]

def _wants_retrieval(text: str) -> bool:
    low = text.lower()
    simple_hits = [
        # COVID
        "covid", "cases", "deaths", "recovered",
        # medicines / fda
        "side effect", "adverse", "reaction", "fda", "medicine", "drug",
        # nutrition / usda
        "nutrition", "usda", "vitamin", "protein", "calcium", "iron",
        # general epi
        "incidence", "prevalence", "mortality", "death rate", "case fatality",
        # world bank-ish
        "life expectancy", "under 5 mortality", "under-5 mortality", "under five mortality",
        "health expenditure", "health spending", "malaria incidence", "tb incidence", "tuberculosis incidence",
        # flu
        "flu", "influenza", "ili"
    ]
    if any(k in low for k in simple_hits):
        return True
    patterns = [
        r"\bunder[- ]?5\b.*\bmortality\b",
        r"\blife expectancy\b",
        r"\bhealth (?:expenditure|spending)\b",
        r"\b(?:malaria|tb|tuberculosis)\s+incidence\b",
        r"\b(death|mortality)\s+rate\b",
    ]
    return any(re.search(p, low) for p in patterns)

def _wants_report(text: str) -> bool:
    low = text.lower()
    report_kw = [
        "report", "graph", "chart", "trend",
        "visualize", "visualise", "time series", "timeseries",
        "generate a report"
    ]
    return any(k in low for k in report_kw)

@app.post("/route/chat")
async def route_chat(body: ChatBody):
    msg = body.message.strip()

    # --- Security PRECHECK (auth + unsafe content check) ---
    if SEC_BASE:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                pre = await client.post(
                    f"{SEC_BASE}/precheck",
                    json={"username": SEC_USER, "password": SEC_PASS, "message": msg},
                )
            pre_data = pre.json()
            if not pre_data.get("ok"):
                # Blocked by security policy – return reason to the UI
                return {
                    "type": "blocked",
                    "summary": pre_data.get("message", "Message blocked by security policy."),
                    "sources": [],
                }
        except Exception:
            # Fail open if security agent is unreachable
            pass

    # 1) Report intent → Report Agent
    if _wants_report(msg):
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{AGENTS['report'].rstrip('/')}/report_from_text",
                json={"query": msg},
            )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)

        data = r.json()
        resp = {
            "type": "report",
            "summary": data.get("summary"),
            "visuals": data.get("visuals", []),
            "report_url": data.get("report_url"),
            "pdf_url": data.get("pdf_url"),
            "sources": data.get("sources", []),
            "disclaimer": data.get("disclaimer"),
        }

    # 2) Retrieval intent → Retrieval Agent
    elif _wants_retrieval(msg):
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{AGENTS['retrieval'].rstrip('/')}/search",
                json={"question": msg},
            )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)

        data = r.json()
        resp = {
            "type": "retrieval",
            "query": data.get("query", {}),
            "facts": data.get("facts", {}),
            "sources": data.get("sources", []),
        }

    # 3) Fallback → canned Chat Agent
    else:
        from agents.chat_agent.engine import get_chat_response
        resp = {"type": "chat", "reply": get_chat_response(msg)}

    # --- Security POSTCHECK (mask + encrypt final user text) ---
    if SEC_BASE:
        try:
            # Choose the best text field to show to the user
            text_for_user = (
                resp.get("summary")
                or (resp.get("facts") or {}).get("summary")
                or resp.get("reply")
                or ""
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                post = await client.post(
                    f"{SEC_BASE}/postcheck",
                    json={"text": text_for_user},
                )
            post_data = post.json()
            # Attach masked + encrypted fields for the frontend (non-breaking)
            resp["summary_masked"] = post_data.get("masked", text_for_user)
            resp["encrypted"] = post_data.get("encrypted", "")
        except Exception:
            # Fail open if security agent is unreachable
            pass

    return resp


async def _security_precheck(text: str) -> dict:
    """
    Call Security Agent /precheck. Returns dict like {"ok": True/False, "message": "..."}
    If the security agent is down, fail open (ok=True) so your demo keeps working.
    """
    if not SEC_BASE:
        return {"ok": True, "message": text}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{SEC_BASE}/precheck",
                json={"username": SEC_USER, "password": SEC_PASS, "message": text},
            )
        return r.json()
    except Exception:
        return {"ok": True, "message": text}  # fail open for resilience

async def _security_postcheck(text: str) -> dict:
    """
    Call Security Agent /postcheck. Returns {"masked": "...", "encrypted": "<fernet token>"}.
    If the agent is down, return the raw text.
    """
    if not SEC_BASE:
        return {"masked": text, "encrypted": ""}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{SEC_BASE}/postcheck", json={"text": text})
        return r.json()
    except Exception:
        return {"masked": text, "encrypted": ""}


@app.post("/route/search")
async def route_search(body: SearchBody):
    q = (body.query or "").strip()
    filters = body.filters or {}

    # 0) Security precheck (send username/password/message per Security Agent schema)
    if SEC_BASE:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                pre = await client.post(
                    f"{SEC_BASE}/precheck",
                    json={"username": SEC_USER, "password": SEC_PASS, "message": q},
                )
            if pre.status_code == 200:
                decision = pre.json()
                if not decision.get("ok", True):
                    return {
                        "type": "search",
                        "query": q,
                        "summary": decision.get("message", "Your query was blocked for safety."),
                        "items": [],
                        "sources": []
                    }
        except Exception:
            # If security service fails, continue (fail-open)
            pass

    # 1) Forward to Retrieval Agent (web mode)
    # 1) Forward to Retrieval Agent (simple mode)
    payload_body = {"question": q}
    if filters:
        payload_body["filters"] = filters  # only if your retrieval agent supports filters

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{RETRIEVAL_BASE}/search",
            json=payload_body,
        )

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    payload = r.json()

    # 2) Optional audit (non-blocking; ignore if /audit doesn't exist)
    if SEC_BASE:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{SEC_BASE}/audit", json={
                    "event": "search",
                    "query": q,
                    "ok": True
                })
        except Exception:
            pass

    return payload

@app.get("/route/search_suggest")
async def route_search_suggest(q: str):
    # 1) Curated health-aware suggestions
    curated = _curated_suggestions(q, max_items=10)
    if curated:
        return {"suggestions": curated}

    # 2) Fallback to Retrieval Agent suggestions (if any)
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{RETRIEVAL_BASE}/suggest", params={"q": q})
    if r.status_code >= 400:
        # fail-soft: no suggestions
        return {"suggestions": []}
    return r.json()

