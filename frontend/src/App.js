import React, { useState, useEffect, useCallback } from "react";
import Editor from "@monaco-editor/react";

import { useSession } from "./hooks/useSession";
import { submitCode, getProfile, getChallenge, getHistory, resetSession } from "./api";
import ProfilePanel from "./components/ProfilePanel";
import AIPanel from "./components/AIPanel";
import HistoryPanel from "./components/HistoryPanel";

// Language → Monaco language ID mapping
const LANGUAGES = [
  { label: "Python", value: "python", monacoId: "python" },
  { label: "JavaScript", value: "javascript", monacoId: "javascript" },
];

const DEFAULT_CODE = {
  python: `# Write your solution here\ndef solution():\n    pass\n`,
  javascript: `// Write your solution here\nfunction solution() {\n\n}\n`,
};

const MONACO_THEME = "vs-dark";

export default function App() {
  const { sessionId, clearSession } = useSession();

  // Editor state
  const [language, setLanguage] = useState("python");
  const [code, setCode] = useState(DEFAULT_CODE.python);
  const [taskDescription, setTaskDescription] = useState("");

  // App state
  const [profile, setProfile] = useState(null);
  const [history, setHistory] = useState([]);
  const [aiResult, setAiResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [leftTab, setLeftTab] = useState("profile"); // "profile" | "history"

  // Challenge overlay
  const [challenge, setChallenge] = useState(null);
  const [challengeLoading, setChallengeLoading] = useState(false);

  // Load profile + history when session is ready
  useEffect(() => {
    if (!sessionId) return;
    refreshProfile();
    refreshHistory();
  }, [sessionId]); // eslint-disable-line

  const refreshProfile = async () => {
    try {
      const res = await getProfile(sessionId);
      setProfile(res.data);
    } catch (e) {
      console.error("profile error", e);
    }
  };

  const refreshHistory = async () => {
    try {
      const res = await getHistory(sessionId);
      setHistory(res.data.submissions || []);
    } catch (e) {
      console.error("history error", e);
    }
  };

  // Language change
  const handleLanguageChange = (e) => {
    const lang = e.target.value;
    setLanguage(lang);
    setCode(DEFAULT_CODE[lang] || "");
    setAiResult(null);
  };

  // Submit
  const handleSubmit = useCallback(async () => {
    if (!sessionId || !code.trim()) return;
    setLoading(true);
    setStatusMsg("Sending to Zen AI…");
    setAiResult(null);
    try {
      const res = await submitCode({
        session_id: sessionId,
        language,
        code,
        task_description: taskDescription,
      });
      setAiResult(res.data);
      setProfile(res.data.profile);
      setStatusMsg(`Score: ${Math.round(res.data.score)}/100`);
      refreshHistory();
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setStatusMsg(`Error: ${detail}`);
    } finally {
      setLoading(false);
    }
  }, [sessionId, language, code, taskDescription]); // eslint-disable-line

  // Generate challenge
  const handleChallenge = async () => {
    if (!sessionId) return;
    setChallengeLoading(true);
    setChallenge(null);
    try {
      const res = await getChallenge(sessionId);
      setChallenge(res.data);
      // Pre-fill editor with starter code
      if (res.data.starter_code) {
        setCode(res.data.starter_code);
      }
      setTaskDescription(res.data.title || "");
    } catch (e) {
      console.error(e);
    } finally {
      setChallengeLoading(false);
    }
  };

  // Reset
  const handleReset = async () => {
    if (!sessionId) return;
    if (!window.confirm("Reset all learning progress for this session?")) return;
    await resetSession(sessionId);
    clearSession();
    setProfile(null);
    setHistory([]);
    setAiResult(null);
    setCode(DEFAULT_CODE[language]);
    setTaskDescription("");
    setStatusMsg("Session reset.");
  };

  // Keyboard shortcut: Ctrl+Enter → submit
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        if (!loading) handleSubmit();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handleSubmit, loading]);

  const monacoLang = LANGUAGES.find((l) => l.value === language)?.monacoId || "python";

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <span className="header-logo">⚡ Zen</span>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Self-Learning Code Editor</span>
        <div className="header-sep" />
        <div className="header-badge">
          <div className="badge-dot" />
          AI Active
        </div>
        {sessionId && (
          <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--mono)" }}>
            {sessionId.slice(0, 8)}…
          </span>
        )}
      </header>

      {/* ── Left sidebar ── */}
      <aside className="sidebar-left">
        <div className="tabs" style={{ borderBottom: "1px solid var(--border)" }}>
          <button className={`tab${leftTab === "profile" ? " active" : ""}`} onClick={() => setLeftTab("profile")}>Profile</button>
          <button className={`tab${leftTab === "history" ? " active" : ""}`} onClick={() => setLeftTab("history")}>History</button>
        </div>

        {leftTab === "profile" ? (
          <>
            <div className="panel-header" style={{ marginTop: 0 }}>
              <span>Learner Profile</span>
            </div>
            <ProfilePanel profile={profile} onReset={handleReset} />
          </>
        ) : (
          <>
            <div className="panel-header">
              <span>Recent Submissions</span>
              <span style={{ color: "var(--text-dim)" }}>{history.length}</span>
            </div>
            <HistoryPanel history={history} />
          </>
        )}
      </aside>

      {/* ── Editor area ── */}
      <main className="editor-area">
        {/* Task + language bar */}
        <div className="task-bar">
          <select value={language} onChange={handleLanguageChange}>
            {LANGUAGES.map((l) => (
              <option key={l.value} value={l.value}>{l.label}</option>
            ))}
          </select>
          <input
            className="task-input"
            placeholder="Task description (optional)…"
            value={taskDescription}
            onChange={(e) => setTaskDescription(e.target.value)}
          />
          <button
            className="btn-ghost"
            onClick={handleChallenge}
            disabled={challengeLoading || !sessionId}
            title="Generate an AI challenge"
          >
            {challengeLoading ? <span className="spinner" /> : "⚡ Challenge"}
          </button>
        </div>

        {/* Challenge card (inline, dismissible) */}
        {challenge && (
          <div style={{ padding: "10px 16px", background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
            <div className="challenge-card" style={{ margin: 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div className="challenge-title">{challenge.title}</div>
                <button className="btn-icon" style={{ marginLeft: 8 }} onClick={() => setChallenge(null)}>✕</button>
              </div>
              <div className="challenge-desc">{challenge.description}</div>
              {challenge.constraints?.length > 0 && (
                <ul className="challenge-constraints">
                  {challenge.constraints.map((c, i) => <li key={i}>{c}</li>)}
                </ul>
              )}
              {challenge.examples?.length > 0 && (
                <div className="challenge-example">
                  <span style={{ color: "var(--text-muted)" }}>ex: </span>
                  {challenge.examples[0].input} → {challenge.examples[0].output}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Monaco editor */}
        <div className="editor-wrapper">
          <Editor
            height="100%"
            language={monacoLang}
            value={code}
            onChange={(val) => setCode(val || "")}
            theme={MONACO_THEME}
            options={{
              fontSize: 14,
              fontFamily: "JetBrains Mono, Fira Code, monospace",
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              lineNumbers: "on",
              renderLineHighlight: "line",
              tabSize: 4,
              automaticLayout: true,
              padding: { top: 12 },
              smoothScrolling: true,
              cursorBlinking: "smooth",
            }}
          />
        </div>

        {/* Footer */}
        <div className="editor-footer">
          <span className="status-bar">{statusMsg || "Ready"}</span>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Ctrl+Enter</span>
            <button
              className="btn-primary"
              onClick={handleSubmit}
              disabled={loading || !sessionId}
            >
              {loading ? <><span className="spinner" /> Analysing…</> : "▶ Analyse"}
            </button>
          </div>
        </div>
      </main>

      {/* ── Right sidebar (AI panel) ── */}
      <aside className="sidebar-right">
        <div className="panel-header">
          <span>Zen AI Feedback</span>
          {aiResult && (
            <span style={{
              fontSize: 11,
              color: aiResult.score >= 75 ? "var(--green)" : aiResult.score >= 45 ? "var(--yellow)" : "var(--red)",
              fontFamily: "var(--mono)",
              fontWeight: 600,
            }}>
              {Math.round(aiResult.score)}/100
            </span>
          )}
        </div>
        <AIPanel result={aiResult} loading={loading} />
      </aside>
    </div>
  );
}
