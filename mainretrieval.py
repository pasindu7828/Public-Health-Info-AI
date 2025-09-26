# backend/retrieval_agent/main.py
from __future__ import annotations
from typing import Any, Dict, Optional, List
from fastapi import FastAPI, HTTPException
from fastapi import Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .agent import InformationRetrievalAgent

app = FastAPI(title="Information Retrieval Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = InformationRetrievalAgent()

# ---- Suggestion data (extend anytime) ----
SUGGEST_DISEASES = [
    "covid-19", "dengue", "malaria", "tuberculosis", "influenza", "hiv", "measles"
]

SUGGEST_COUNTRIES = [
    "Sri Lanka", "India", "World", "United States", "Pakistan",
    "Bangladesh", "Nepal", "China", "Japan", "Australia", "Canada",
    "United Kingdom", "France", "Germany", "Spain", "Italy", "Indonesia"
]


class SearchBody(BaseModel):
    question: str
    mode: Optional[str] = None   # "web" triggers web/data search output format
    filters: Optional[Dict[str, Any]] = None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/search")
def search(body: SearchBody):
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty question")

    # "web" mode → unified search envelope
    if (body.mode or "").lower() == "web":
        result = agent.web_search(q, body.filters or {})
        return result

    # legacy/normal path (your existing JSON outputs)
    return agent.search(q)

@app.get("/suggest")
def suggest(q: str = Query("", description="User's partial query")):
    """
    Returns up to ~15 human-friendly suggestions like:
      - "covid-19 in Sri Lanka"
      - "dengue in India"
      - "malaria in World"
    Filtered by the user's prefix `q` (case-insensitive).
    """
    prefix = (q or "").strip().lower()

    # Build templates
    all_templates = []
    for d in SUGGEST_DISEASES:
        for c in SUGGEST_COUNTRIES:
            all_templates.append(f"{d} in {c}")

    # Filter by prefix if provided
    if prefix:
        items = [s for s in all_templates if s.lower().startswith(prefix)]
        # If nothing matches strictly, try contains
        if not items:
            items = [s for s in all_templates if prefix in s.lower()]
    else:
        # sensible defaults when user hasn't typed yet
        items = [
            "covid-19 in Sri Lanka", "covid-19 in India", "covid-19 in World",
            "dengue in Sri Lanka", "dengue in India", "malaria in World",
        ]

    # Keep it short
    items = items[:15]
    return {"suggestions": items}
