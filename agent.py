# backend/retrieval_agent/agent.py
from __future__ import annotations

from typing import Any, Dict, List
import re
import requests
import spacy
from urllib.parse import quote  # <-- needed
from .adapters.base import FactsAdapter
from .adapters.cdc_flu import CDCFluAdapter
from .adapters.worldbank import WorldBankAdapter

nlp = spacy.load("en_core_web_sm")

# Small country-name -> ISO2 fallback mapping for disease.sh
_ISO2_MAP = {
    "sri lanka": "LK",
    "india": "IN",
    "united states": "US",
    "u.s.": "US",
    "us": "US",
    "usa": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "bangladesh": "BD",
    "pakistan": "PK",
    "nepal": "NP",
    "china": "CN",
    "japan": "JP",
    "australia": "AU",
    "canada": "CA",
    "france": "FR",
    "germany": "DE",
    "spain": "ES",
    "italy": "IT",
    "indonesia": "ID",
}

def _to_iso2_or_original(name: str) -> str:
    if not name:
        return name
    s = name.strip().lower()
    return _ISO2_MAP.get(s, name)


class InformationRetrievalAgent:
    def __init__(self):
        self.covid_api = "https://disease.sh/v3/covid-19/countries/"
        self.medicine_api = "https://api.fda.gov/drug/event.json?search=patient.drug.medicinalproduct:"
        self.usda_api = "https://api.nal.usda.gov/fdc/v1/foods/search"
        # NOTE: consider reading from env instead of hard-coding
        self.usda_api_key = "yUHeDOCO81Ht367aOuHLyppQN8zlnYrGWh7nA4Gp"

        self.known_medicines = ["ibuprofen", "paracetamol", "aspirin", "acetaminophen", "amoxicillin"]
        self.known_diseases = ["covid", "dengue", "malaria", "diabetes", "hypertension", "flu", "influenza"]

        # Adapters (order matters)
        self.adapters: List[FactsAdapter] = [
            CDCFluAdapter(),
            WorldBankAdapter(),
        ]

    # ----------------- Keyword extraction -----------------
    def extract_keywords(self, question: str) -> Dict[str, Any]:
        doc = nlp(question)
        disease = None
        medicine = None
        info_type = None
        country = None

        for ent in doc.ents:
            if ent.label_ == "GPE":
                country = ent.text

        ql = question.lower()
        for d in self.known_diseases:
            if d in ql:
                disease = d
                break

        for m in self.known_medicines:
            if m in ql:
                medicine = m
                break

        if any(word in ql for word in ["side effect", "adverse", "reaction"]):
            info_type = "side_effects"
        elif any(word in ql for word in ["cases", "infected", "infection"]):
            info_type = "cases"
        elif any(word in ql for word in ["death", "deaths"]):
            info_type = "deaths"
        elif any(word in ql for word in ["recovered"]):
            info_type = "recovered"
        elif any(word in ql for word in ["treatment", "dose", "dosage"]):
            info_type = "treatment"
        elif any(word in ql for word in ["symptoms"]):
            info_type = "symptoms"
        elif any(word in ql for word in ["nutrition", "diet", "food", "vitamin"]):
            info_type = "nutrition"
        elif any(word in ql for word in ["habit", "exercise", "healthy"]):
            info_type = "healthy_habits"
        else:
            info_type = "general"

        return {
            "question": question,
            "disease": disease,
            "medicine": medicine,
            "info_type": info_type,
            "country": country,
            "region": country,  # normalize key others use
        }

    # ----------------- Built-in fetchers -----------------
    def fetch_covid_data(self, country="World", info_type="all"):
        """
        Returns a normalized payload:
          { "type": "covid_*", "summary": "...", "data": {...} }
        """
        country_enc = quote(str(country).strip())
        url = f"{self.covid_api}{country_enc}"

        try:
            r = requests.get(url, timeout=20)
            if r.status_code >= 400:
                iso2 = _to_iso2_or_original(country)
                url_iso = f"{self.covid_api}{quote(iso2)}?strict=true"
                r = requests.get(url_iso, timeout=20)

            r.raise_for_status()
            data = r.json()

            if info_type == "cases":
                return {
                    "type": "covid_cases",
                    "summary": f"{data.get('country', country)} — {data.get('cases')} total COVID cases ({data.get('todayCases', 0)} today).",
                    "data": {"country": data.get("country", country),
                             "cases": data.get("cases"),
                             "todayCases": data.get("todayCases", 0)},
                    "sources": [{"name": "disease.sh (JHU)", "url": "https://disease.sh/"}],
                }
            elif info_type == "deaths":
                return {
                    "type": "covid_deaths",
                    "summary": f"{data.get('country', country)} — {data.get('deaths')} total COVID deaths ({data.get('todayDeaths', 0)} today).",
                    "data": {"country": data.get("country", country),
                             "deaths": data.get("deaths"),
                             "todayDeaths": data.get("todayDeaths", 0)},
                    "sources": [{"name": "disease.sh (JHU)", "url": "https://disease.sh/"}],
                }
            elif info_type == "recovered":
                return {
                    "type": "covid_recovered",
                    "summary": f"{data.get('country', country)} — {data.get('recovered')} recovered.",
                    "data": {"country": data.get("country", country),
                             "recovered": data.get("recovered")},
                    "sources": [{"name": "disease.sh (JHU)", "url": "https://disease.sh/"}],
                }

            # default: include full data but still normalized
            return {
                "type": "covid_all",
                "summary": f"COVID-19 data for {data.get('country', country)} retrieved.",
                "data": data,
                "sources": [{"name": "disease.sh (JHU)", "url": "https://disease.sh/"}],
            }

        except Exception as e:
            return {
                "type": "covid_error",
                "summary": f"COVID-19 data for {country} could not be fetched.",
                "data": {"error": str(e)},
                "sources": [{"name": "disease.sh (JHU)", "url": "https://disease.sh/"}],
            }

    def fetch_medicine_info(self, medicine_name, info_type="general"):
        if not medicine_name:
            return {
                "type": "medicine_error",
                "summary": "No medicine specified.",
                "data": {},
                "sources": [],
            }
        try:
            med_query = re.sub(r"\s+", "+", medicine_name)
            url = self.medicine_api + med_query + "&limit=20"
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            data = response.json()

            reactions = []
            for result in data.get("results", []):
                for r in result.get("patient", {}).get("reaction", []):
                    name = r.get("reactionmeddrapt")
                    if name:
                        reactions.append(name.strip())

            from collections import Counter
            counts = Counter([x.lower() for x in reactions])
            top = [name for name, _ in counts.most_common(6)]
            pretty = ", ".join(top) if top else "No common side effects found."

            return {
                "type": "medicine_side_effects",
                "summary": f"Commonly reported side effects for {medicine_name}: {pretty}.",
                "data": {"medicine": medicine_name, "side_effects": sorted(set(reactions))},
                "sources": [{"name": "FDA (openFDA)", "url": "https://open.fda.gov/apis/drug/event/"}],
            }

        except Exception as e:
            return {
                "type": "medicine_error",
                "summary": f"Could not fetch medicine info for {medicine_name}.",
                "data": {"error": str(e)},
                "sources": [{"name": "FDA (openFDA)", "url": "https://open.fda.gov/apis/drug/event/"}],
            }

    def fetch_nutrition_info(self, query_text: str):
        """
        Look up foods from USDA FoodData Central and build a friendly summary that
        lists the top 3 foods for several key nutrients (when available).
        Returns:
        {
            "type": "nutrition",
            "summary": <string>,                  # human-friendly lines
            "results": [ {food_name, nutrients} ],
            "summary_table": [
            {
                "Nutrient": <str>,
                "Top Foods": [ {"food_name": <str>, "amount": <float>} , ... up to 3 ]
            },
            ...
            ]
        }
        On failure:
        {
            "type": "nutrition_error",
            "summary": "USDA query failed (check key/limit/network).",
            "error": <str>
        }
        """
        try:
            # --- 1) Primary query ---
            params = {"query": query_text, "api_key": self.usda_api_key, "pageSize": 8}
            response = requests.get(self.usda_api, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
            foods = data.get("foods", []) or []

            # --- 1b) Simple fallback keyword if no hits ---
            if not foods:
                qlow = (query_text or "").lower()
                fallback = None
                if "vitamin c" in qlow or "ascorbic" in qlow:
                    fallback = "vitamin c"
                elif "protein" in qlow:
                    fallback = "protein"
                elif "iron" in qlow:
                    fallback = "iron"
                elif "calcium" in qlow:
                    fallback = "calcium"

                if fallback:
                    response = requests.get(
                        self.usda_api,
                        params={"query": fallback, "api_key": self.usda_api_key, "pageSize": 8},
                        timeout=20,
                    )
                    response.raise_for_status()
                    data = response.json()
                    foods = data.get("foods", []) or []

            # --- 2) Normalize results: [{food_name, nutrients{...}}] ---
            results = []
            for item in foods:
                food_name = item.get("description")
                nutrients = {
                    n.get("nutrientName"): n.get("value")
                    for n in (item.get("foodNutrients") or [])
                    if n and n.get("nutrientName") is not None
                }
                results.append({"food_name": food_name, "nutrients": nutrients})

            if not results:
                return {
                    "type": "nutrition",
                    "summary": "No USDA foods matched that query.",
                    "results": [],
                    "summary_table": [],
                }

            # --- 3) Build top-3 list for each key nutrient ---
            key_nutrients = [
                "Vitamin C, total ascorbic acid",
                "Protein",
                "Calcium, Ca",
                "Iron, Fe",
                "Vitamin A, RAE",
            ]

            def _fmt_amount(v):
                try:
                    # keep small decimals readable, big numbers as ints
                    fv = float(v)
                    return int(fv) if abs(fv - int(fv)) < 1e-6 else round(fv, 2)
                except Exception:
                    return v

            summary_table = []
            for nutrient in key_nutrients:
                foods_with_nutrient = [
                    {
                        "food_name": r["food_name"],
                        "amount": r["nutrients"].get(nutrient, 0) or 0,
                    }
                    for r in results
                ]
                # Only keep > 0 values
                foods_with_nutrient = [f for f in foods_with_nutrient if (f["amount"] or 0) > 0]
                foods_with_nutrient.sort(key=lambda x: x["amount"], reverse=True)

                if foods_with_nutrient:
                    top_foods = [
                        {"food_name": f["food_name"], "amount": _fmt_amount(f["amount"])}
                        for f in foods_with_nutrient[:3]
                    ]
                    summary_table.append({"Nutrient": nutrient, "Top Foods": top_foods})

            # --- 4) Human-friendly multi-line summary ---
            if summary_table:
                lines = []
                for row in summary_table:
                    foods_str = ", ".join(
                        f"{f['food_name']} ({f['amount']})" for f in row["Top Foods"]
                    )
                    lines.append(f"{row['Nutrient']}: {foods_str}")
                facts_summary = "Top nutrient-rich foods:\n" + "\n".join(lines)
            else:
                facts_summary = "USDA results found, but no notable amounts for the selected nutrients."

            return {
                "type": "nutrition",
                "summary": facts_summary,
                "results": results,
                "summary_table": summary_table,
            }

        except Exception as e:
            return {
                "type": "nutrition_error",
                "summary": "USDA query failed (check key/limit/network).",
                "error": str(e),
            }

    # ----------------- Routing -----------------
    def search(self, question: str) -> Dict[str, Any]:
        """
        Returns a uniform envelope for the orchestrator/front-end:
        {
            "type": "retrieval",
            "query": <parsed query>,
            "facts": <normalized payload from adapter/builtin>,
            "summary": <string>,
            "sources": [ {name, url}, ... ]
        }
        """
        query = self.extract_keywords(question)

        # 1) Try adapters first
        for adapter in self.adapters:
            try:
                if adapter.supports(query):
                    result = adapter.fetch(query)  # {type, summary, data, sources?}
                    return {
                        "type": "retrieval",
                        "query": query,
                        "facts": result,
                        "summary": result.get("summary", ""),
                        "sources": result.get("sources", []),
                    }
            except Exception as e:
                return {
                    "type": "retrieval",
                    "query": query,
                    "facts": {"type": "adapter_error", "data": {"error": str(e)}},
                    "summary": f"{adapter.__class__.__name__} failed to fetch data.",
                    "sources": [],
                }

        # 2) Built-ins
        if query.get("disease") == "covid":
            payload = self.fetch_covid_data(query.get("country") or "World", query.get("info_type"))
            return {
                "type": "retrieval",
                "query": query,
                "facts": payload,
                "summary": payload.get("summary", ""),
                "sources": payload.get("sources", []),
            }

        if query.get("medicine"):
            payload = self.fetch_medicine_info(query["medicine"], query.get("info_type"))
            return {
                "type": "retrieval",
                "query": query,
                "facts": payload,
                "summary": payload.get("summary", ""),
                "sources": payload.get("sources", []),
            }

        if query.get("info_type") == "nutrition":
            payload = self.fetch_nutrition_info(question)
            return {
                "type": "retrieval",
                "query": query,
                "facts": payload,
                "summary": payload.get("summary", ""),
                "sources": payload.get("sources", []),
            }

        # 3) Fallback
        return {
            "type": "retrieval",
            "query": query,
            "facts": {"type": "general_health", "data": {"info": "No structured adapter matched."}},
            "summary": "I couldn't match that to a real-world data source, but I can try a general answer.",
            "sources": [],
        }

    # -------- NEW: simple web/data search path for orchestrator --------
    def web_search(self, question: str, filters: dict) -> Dict[str, Any]:
        """
        Returns a unified 'search' envelope:
        {
          "type": "search",
          "query": "...",
          "summary": "...multi-sentence explanation...",
          "items": [ {title, snippet, url, source}, ... ],
          "sources": [ {name, url}, ... ]
        }
        Strategy:
          1) Try adapters (CDC/WHO/WorldBank/USDA/FDA) – normalize to items[]
          2) If nothing suitable, fallback to Wikipedia summary
        """
        q = (question or "").strip()
        items: List[Dict[str, Any]] = []
        sources: List[Dict[str, str]] = []

        # 1) Try adapters that already know how to fetch real data and we can normalize
        # We’ll reuse your adapter list but collect "items" instead of raw payloads
        for adapter in self.adapters:
            try:
                parsed = self.extract_keywords(q)
                if adapter.supports(parsed):
                    payload = adapter.fetch(parsed)
                    # Normalize to search items
                    # WorldBankAdapter returns: {type, summary, data:{title,series,...}, sources:[...]}
                    title = payload.get("data", {}).get("title") or payload.get("type") or "Result"
                    snippet = payload.get("summary") or "Data retrieved."
                    # pick 1st source url if present
                    src_list = payload.get("sources") or []
                    first_url = src_list[0]["url"] if src_list and "url" in src_list[0] else None
                    source_name = (src_list[0]["name"] if src_list else "Data source")

                    items.append({
                        "title": title,
                        "snippet": snippet,
                        "url": first_url or "",
                        "source": source_name
                    })
                    sources.extend(src_list)
                    break
            except Exception:
                # ignore adapter errors here; we’ll fallback
                pass

        # 2) If still empty → Wikipedia fallback (good generic explainer)
        if not items:
            try:
                # Very small heuristic: use the first 6 words for a title-y query
                import re, requests
                topic = re.sub(r"\s+", " ", q).strip()
                titleish = topic.split("?")[0].strip()
                # Call Wikipedia REST summary
                api_title = titleish.replace(" ", "_")
                url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{api_title}"
                r = requests.get(url, timeout=12)
                if r.status_code == 200:
                    js = r.json()
                    extract = js.get("extract")
                    page_url = js.get("content_urls", {}).get("desktop", {}).get("page")
                    if extract and page_url:
                        items.append({
                            "title": js.get("title", titleish),
                            "snippet": extract,
                            "url": page_url,
                            "source": "Wikipedia"
                        })
                        sources.append({"name": "Wikipedia", "url": page_url})
            except Exception:
                pass

        # Build a multi-sentence, user-friendly summary
        if items:
            first = items[0]
            core = first["snippet"]
            # Trim long snippets for the summary, but keep nice flow (2–4 sentences)
            summary = (
                f"Here’s what I found about “{q}”. "
                f"{core} "
                f"I included a primary reference from {first['source']}"
                f"{' and additional sources' if len(items) > 1 else ''}. "
                f"Open the links below for full details."
            )
        else:
            summary = (
                f"I looked for reliable sources about “{q}” but didn’t find a good match. "
                f"Try rephrasing or be more specific (e.g., add a country, year, or health topic)."
            )

        return {
            "type": "search",
            "query": q,
            "summary": summary,
            "items": items,
            "sources": sources,
        }

    def suggest(self, q: str) -> Dict[str, Any]:
        """
        Very simple suggester (you can enhance later by edge n-grams or static dictionaries).
        Returns up to ~8 suggestions relevant to health topics.
        """
        base = [
            "vitamin a", "vitamin b12", "vitamin c", "vitamin d",
            "iron deficiency", "calcium rich foods", "protein intake",
            "covid cases", "covid deaths", "influenza trend",
            "life expectancy", "under 5 mortality", "health expenditure",
            "dengue symptoms", "malaria prevention", "tb incidence",
        ]
        ql = (q or "").strip().lower()
        if not ql:
            return {"suggestions": base[:8]}

        out = [s for s in base if ql in s.lower()]
        # If nothing matches, still return a couple of helpful ideas
        if not out:
            out = base[:5]
        return {"suggestions": out[:8]}
