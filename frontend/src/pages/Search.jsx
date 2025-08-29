// src/pages/Search.jsx
import Sidebar from "../components/Sidebar";
import Header from "../components/Header";
import "../styles/layout.css";
import "../styles/search.css";
import { useState, useEffect, useRef } from "react";
import { composeReadableSummary } from "../utils/formatters";

export default function Search() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  // suggestions
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggest, setShowSuggest] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isFocused, setIsFocused] = useState(false);
  const [lastSearched, setLastSearched] = useState(""); // prevent re-suggesting same term

  const inputRef = useRef(null);
  const debounceRef = useRef(null);
  const abortRef = useRef(null);

  async function handleSearch(e) {
    e?.preventDefault?.();
    const q = query.trim();
    if (!q) return;

    // stop suggestions immediately
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (abortRef.current) abortRef.current.abort();
    setShowSuggest(false);
    setActiveIndex(-1);

    setLoading(true);
    setError("");
    setResult(null);
    setLastSearched(q);

    try {
      const r = await fetch(`http://127.0.0.1:8010/route/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });
      const data = await r.json();
      setResult(data);
    } catch (err) {
      setError(err.message || "Search failed");
    } finally {
      setLoading(false);
    }
  }

  // Debounced suggestions: only when focused, not loading, and query changed since last search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!isFocused || loading) return;

    const q = query.trim();
    if (q.length < 2 || q === lastSearched) {
      setSuggestions([]);
      setShowSuggest(false);
      setActiveIndex(-1);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      try {
        // cancel previous request if still running
        if (abortRef.current) abortRef.current.abort();
        abortRef.current = new AbortController();

        const res = await fetch(
          `http://127.0.0.1:8010/route/search_suggest?q=${encodeURIComponent(q)}`,
          { signal: abortRef.current.signal }
        );
        const data = await res.json();
        const list = Array.isArray(data?.suggestions) ? data.suggestions : [];
        setSuggestions(list);
        setShowSuggest(list.length > 0);
        setActiveIndex(-1);
      } catch {
        // swallow abort and network errors
        setSuggestions([]);
        setShowSuggest(false);
        setActiveIndex(-1);
      }
    }, 220);

    return () => clearTimeout(debounceRef.current);
  }, [query, isFocused, loading, lastSearched]);

  function pickSuggestion(text) {
    setQuery(text);
    setShowSuggest(false);
    setActiveIndex(-1);
    // if you want auto-search after pick, uncomment:
    // handleSearch();
  }

  function onKeyDown(e) {
    if (!showSuggest || suggestions.length === 0) {
      if (e.key === "Enter") handleSearch(e);
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (activeIndex >= 0) pickSuggestion(suggestions[activeIndex]);
      else handleSearch(e);
    } else if (e.key === "Escape") {
      setShowSuggest(false);
      setActiveIndex(-1);
    }
  }

  function onBlur() {
    // close a tick later so clicks on list still register (mousedown)
    setTimeout(() => {
      setIsFocused(false);
      setShowSuggest(false);
      setActiveIndex(-1);
    }, 100);
  }

  const niceSummary = composeReadableSummary(result);
  const facts = result?.facts;
  const covid = facts?.type === "covid_all" ? facts.data : null;

  return (
    <div className="app-shell">
      <Sidebar />
      <Header />

      <main className="app-main">
        <section className="search">
          <h1 className="search__title">Search Health Related Things</h1>

          <form className="search__bar" onSubmit={handleSearch} autoComplete="off">
            <span className="search__icon" aria-hidden="true">🔍</span>
            <input
              ref={inputRef}
              type="text"
              placeholder="covid 19 in sri lanka…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              onFocus={() => setIsFocused(true)}
              onBlur={onBlur}
              className="search__input"
              role="combobox"
              aria-expanded={showSuggest}
              aria-autocomplete="list"
              aria-controls="search-suggest-list"
            />
            {showSuggest && suggestions.length > 0 && (
              <ul id="search-suggest-list" className="search__suggest" role="listbox">
                {suggestions.map((s, i) => (
                  <li
                    key={s + i}
                    role="option"
                    aria-selected={activeIndex === i}
                    className={`search__suggest-item ${activeIndex === i ? "is-active" : ""}`}
                    onMouseDown={() => pickSuggestion(s)}
                    onMouseEnter={() => setActiveIndex(i)}
                  >
                    {s}
                  </li>
                ))}
              </ul>
            )}
            <button type="submit" className="search__btn">
              Search
            </button>
          </form>

          {loading && <div className="sr__loading">Looking that up…</div>}
          {error && <div className="sr__error">{error}</div>}

          {result && (
            <div className="sr__results">
              <div className="sr__retrieval">
                {niceSummary && (
                  <p className="sr__summary sr__summary--narrative">{niceSummary}</p>
                )}

                {covid && (
                  <div className="sr__table-wrap">
                    <table className="sr__table">
                      <tbody>
                        <tr><th>Total cases</th><td>{covid.cases?.toLocaleString?.() ?? covid.cases}</td></tr>
                        <tr><th>New cases (today)</th><td>{covid.todayCases?.toLocaleString?.() ?? covid.todayCases}</td></tr>
                        <tr><th>Total deaths</th><td>{covid.deaths?.toLocaleString?.() ?? covid.deaths}</td></tr>
                        <tr><th>New deaths (today)</th><td>{covid.todayDeaths?.toLocaleString?.() ?? covid.todayDeaths}</td></tr>
                        <tr><th>Recovered</th><td>{covid.recovered?.toLocaleString?.() ?? covid.recovered}</td></tr>
                        <tr><th>Active</th><td>{covid.active?.toLocaleString?.() ?? covid.active}</td></tr>
                        <tr><th>Tests</th><td>{covid.tests?.toLocaleString?.() ?? covid.tests}</td></tr>
                      </tbody>
                    </table>
                  </div>
                )}

                {Array.isArray(result.sources) && result.sources.length > 0 && (
                  <div className="sr__sources">
                    <span>Sources:</span>
                    {result.sources.map((s, i) => (
                      <a key={i} href={s.url} target="_blank" rel="noreferrer">{s.name}</a>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
