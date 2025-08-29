import { useRef, useState, useEffect } from "react";
import Sidebar from "../components/Sidebar";
import Header from "../components/Header";
import "../styles/layout.css";
import "../styles/generate.css";
import { reportFromText } from "../lib/api";

const API_BASE = import.meta.env.VITE_API_BASE;

export default function Generate() {
  const [tab, setTab] = useState("text"); // "text" | "form"
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const resultRef = useRef(null);

  useEffect(() => {
    // After a successful result, scroll it into view
    if (result && resultRef.current) {
      resultRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [result]);

  async function handleGenerate() {
    setError("");
    setResult(null);

    const text = (prompt || "").trim();
    if (text.length < 8) {
      setError("Please describe your request (at least 8 characters).");
      return;
    }

    try {
      setLoading(true);
      const data = await reportFromText(text);
      setResult(data);
    } catch (e) {
      setError(e.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <Header />

      <main className="app-main">
        <section className="generate">
          <h1 className="generate__title">Generate Reports</h1>

          {/* Tabs */}
          <div className="generate-tabs" role="tablist" aria-label="Generate modes">
            <div
              role="tab"
              aria-selected={tab === "text"}
              tabIndex={0}
              onClick={() => setTab("text")}
              onKeyDown={(e) => e.key === "Enter" && setTab("text")}
              className={`generate-tab ${tab === "text" ? "generate-tab--active" : ""}`}
            >
              Text Prompts
            </div>
            <div
              role="tab"
              aria-selected={tab === "form"}
              tabIndex={0}
              onClick={() => setTab("form")}
              onKeyDown={(e) => e.key === "Enter" && setTab("form")}
              className={`generate-tab ${tab === "form" ? "generate-tab--active" : ""}`}
            >
              Structured Form
            </div>
          </div>

          {/* TEXT TAB */}
          {tab === "text" && (
            <>
              <label htmlFor="gen-input" className="generate__label">
                Enter what you want to generate
              </label>

              <textarea
                id="gen-input"
                className="generate__textarea"
                placeholder='e.g., "Generate a dengue report for Sri Lanka from 2025-07-01 to 2025-08-24 using WHO"'
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />

              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <button
                  className="generate-btn"
                  type="button"
                  onClick={handleGenerate}
                  disabled={loading}
                >
                  {loading ? "Generating…" : "Generate"}
                </button>

                {/* Optional clear */}
                <button
                  type="button"
                  className="btn-link-clear"
                  onClick={() => {
                    setPrompt("");
                    setResult(null);
                    setError("");
                  }}
                  disabled={loading}
                  style={{ background: "#e8eef6", color: "#0b1320" }}
                >
                  Clear
                </button>
              </div>

              {/* Error message */}
              {error && (
                <div className="error-banner" role="alert" aria-live="polite" style={{ marginTop: 12 }}>
                  {error}
                </div>
              )}

              {/* Skeletons while loading */}
              {loading && (
                <div className="result-panel" style={{ marginTop: 18 }}>
                  <div className="result-card skeleton">
                    <div className="skeleton-line" style={{ width: "60%" }} />
                    <div className="skeleton-line" style={{ width: "90%" }} />
                    <div className="skeleton-line" style={{ width: "80%" }} />
                  </div>
                  <div className="result-card skeleton" style={{ height: 280 }}>
                    <div className="skeleton-block" style={{ width: "100%", height: "100%" }} />
                  </div>
                </div>
              )}

              {/* Results */}
              {result && !loading && (
                <div className="result-panel" ref={resultRef}>
                  <div className="result-card">
                    <h2 className="result-title">Summary</h2>
                    <p className="result-text">{result.summary}</p>
                  </div>

                  {/* Chart (if present) */}
                  {Array.isArray(result.visuals) &&
                    result.visuals.length > 0 &&
                    result.visuals[0]?.path && (
                      <div className="result-card">
                        <h3 className="result-subtitle">Trend</h3>
                        <img
                          className="result-chart"
                          src={`${API_BASE}${result.visuals[0].path}`}
                          alt="Trend chart"
                        />
                      </div>
                    )}

                  {/* Sources */}
                  {Array.isArray(result.sources) && result.sources.length > 0 && (
                    <div className="result-card">
                      <h3 className="result-subtitle">Sources</h3>
                      <ul className="result-sources">
                        {result.sources.map((s, idx) => (
                          <li key={idx}>
                            <a href={s.url} target="_blank" rel="noreferrer">
                              {s.name || s.url}
                            </a>
                            {s.date ? ` (${s.date})` : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="result-actions">
                    {result.report_url && (
                      <a
                        className="btn-link"
                        href={`${API_BASE}${result.report_url}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View Report
                      </a>
                    )}
                    {result.pdf_url ? (
                      <a
                        className="btn-link"
                        href={`${API_BASE}${result.pdf_url}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Download PDF
                      </a>
                    ) : (
                      <button className="btn-link btn-link--disabled" disabled>
                        PDF not available
                      </button>
                    )}
                  </div>

                  {/* Disclaimer */}
                  {result.disclaimer && (
                    <p className="result-disclaimer">{result.disclaimer}</p>
                  )}
                </div>
              )}
            </>
          )}

          {/* STRUCTURED TAB placeholder (wire later) */}
          {tab === "form" && (
            <div className="structured-placeholder">
              <p>Structured form coming next (Disease, Region, Dates, Sources).</p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
