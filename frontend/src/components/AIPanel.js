import React, { useState } from "react";
import ReactMarkdown from "react-markdown";

function ScoreCircle({ score }) {
  const cls = score >= 75 ? "high" : score >= 45 ? "mid" : "low";
  return (
    <div className="ai-score-ring">
      <div className={`score-circle ${cls}`}>{Math.round(score)}</div>
      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>out of 100</div>
    </div>
  );
}

export default function AIPanel({ result, loading }) {
  const [tab, setTab] = useState("feedback");

  if (loading) {
    return (
      <div className="ai-panel" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14 }}>
        <div className="spinner" style={{ width: 28, height: 28 }} />
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Analysing your code…</div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="ai-panel">
        <div className="ai-idle">
          <div className="ai-idle-icon">🤖</div>
          <div style={{ fontWeight: 600, color: "var(--text-dim)", fontSize: 13 }}>Zen AI</div>
          <div style={{ fontSize: 12, lineHeight: 1.7 }}>
            Write or paste code, then click <strong style={{ color: "var(--accent)" }}>Analyse</strong> to get adaptive feedback based on your learning history.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
      <div className="tabs">
        {["feedback", "tests", "next"].map((t) => (
          <button key={t} className={`tab${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>
            {t === "feedback" ? "Feedback" : t === "tests" ? "Test Cases" : "Next"}
          </button>
        ))}
      </div>

      <div className="ai-panel">
        {tab === "feedback" && (
          <>
            <ScoreCircle score={result.score} />

            {/* Summary */}
            <div className="ai-section">
              <div className="ai-section-title">Summary</div>
              <div className="ai-summary">{result.summary}</div>
            </div>

            {/* Mistakes */}
            {result.mistakes?.length > 0 && (
              <div className="ai-section">
                <div className="ai-section-title">Issues Found</div>
                <div className="tag-list">
                  {result.mistakes.map((m) => (
                    <span key={m} className="tag" style={{ borderColor: "rgba(248,113,113,0.3)", color: "var(--red)" }}>
                      {m.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Hint */}
            {result.hint && (
              <div className="ai-section">
                <div className="ai-section-title">Personalised Hint</div>
                <div className="ai-hint">{result.hint}</div>
              </div>
            )}

            {/* Detailed feedback */}
            {result.feedback && (
              <div className="ai-section">
                <div className="ai-section-title">Detailed Feedback</div>
                <div className="feedback-md">
                  <ReactMarkdown>{result.feedback}</ReactMarkdown>
                </div>
              </div>
            )}
          </>
        )}

        {tab === "tests" && (
          <div className="ai-section">
            <div className="ai-section-title">Suggested Test Cases</div>
            {result.test_cases?.length > 0 ? (
              result.test_cases.map((tc, i) => (
                <div key={i} className="test-case">
                  <div className="test-case-label">Case {i + 1}</div>
                  <div className="test-io">
                    <span style={{ color: "var(--text-muted)" }}>in: </span>
                    {tc.input}
                  </div>
                  <div className="test-io">
                    <span style={{ color: "var(--text-muted)" }}>out: </span>
                    {tc.expected}
                  </div>
                  {tc.explanation && (
                    <div className="test-explain">{tc.explanation}</div>
                  )}
                </div>
              ))
            ) : (
              <div className="empty-state">No test cases generated.</div>
            )}
          </div>
        )}

        {tab === "next" && (
          <div className="ai-section">
            <div className="ai-section-title">Suggested Next Challenge</div>
            {result.next_challenge ? (
              <div className="next-challenge">{result.next_challenge}</div>
            ) : (
              <div className="empty-state">Submit code to get a personalised next challenge.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
