import React, { useState } from "react";

const STATES = [
  { id: "observe", label: "Observe", icon: "👁️" },
  { id: "diagnose", label: "Diagnose", icon: "🔍" },
  { id: "plan", label: "Plan", icon: "📋" },
  { id: "patch", label: "Patch", icon: "🛠️" },
  { id: "verify", label: "Verify", icon: "🧪" },
  { id: "success", label: "Success", icon: "✅" },
];

const STATE_ORDER = ["observe", "diagnose", "plan", "patch", "verify", "success"];

export function AgentPanel({
  agentState,
  agentStatus,
  activeSession,
  onStartSession,
  lastDiff,
  memory,
  strategy,
  memorySaved,
  explanation,
}) {
  const [commandInput, setCommandInput] = useState("");

  const handleStart = (e) => {
    e.preventDefault();
    if (commandInput.trim()) {
      onStartSession(commandInput.trim());
    }
  };

  const isSuccess = agentStatus === "success" || agentState === "success";
  const isFailure = agentStatus === "failed" || agentStatus === "escalated" || agentState === "failure";
  const isActive = agentStatus === "active";

  return (
    <div className="agent-panel">
      <div className="agent-panel-header">
        <div className="agent-title">
          <span className="agent-icon">🤖</span>
          <h2>Autonomous Agent</h2>
        </div>
        <div className={`status-pill status-${agentStatus || "idle"}`}>
          {(agentStatus || "idle").toUpperCase()}
        </div>
      </div>

      {/* State Machine Stepper */}
      <div className="state-stepper">
        {STATES.map((st, idx) => {
          const currentIdx = STATE_ORDER.indexOf(agentState);
          const stepIdx = STATE_ORDER.indexOf(st.id);
          const isCompleted = isSuccess || (isActive && stepIdx < currentIdx && currentIdx !== -1);
          const isActive2 = agentState === st.id && !isSuccess && !isFailure;

          return (
            <div key={st.id} className={`step-item ${isActive2 ? "active" : ""} ${isCompleted ? "completed" : ""} ${isFailure && stepIdx <= currentIdx ? "failed" : ""}`}>
              <span className="step-icon">{isCompleted ? "✅" : isFailure && stepIdx <= currentIdx ? "❌" : st.icon}</span>
              <span className="step-label">{st.label}</span>
            </div>
          );
        })}
      </div>

      {/* Plain English Root Cause & Code Fix Card */}
      {explanation && (
        <div className="card explanation-card">
          <div className="explanation-header">
            <span className="explanation-icon">💡</span>
            <h3>Root Cause & Code Fix Summary</h3>
          </div>

          <div className="explanation-section fail-section">
            <div className="explanation-title fail-title">
              <span className="bullet-icon">❌</span>
              <strong>Why Your Code Failed:</strong>
            </div>
            <p className="explanation-text fail-text">{explanation.why_failed}</p>
          </div>

          <div className="explanation-section fix-section">
            <div className="explanation-title fix-title">
              <span className="bullet-icon">🛠️</span>
              <strong>What Code Was Fixed:</strong>
            </div>
            <p className="explanation-text fix-text">{explanation.what_fixed}</p>
            {explanation.files_modified && explanation.files_modified.length > 0 && (
              <div className="modified-files-tag">
                <span>Modified Files:</span>
                {explanation.files_modified.map((f, i) => (
                  <span key={i} className="file-tag">📄 {f}</span>
                ))}
              </div>
            )}
            {explanation.verified_output && (
              <div className="verified-output-tag">
                <span>Verified Clean Output:</span>
                <code>{explanation.verified_output}</code>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Memory Panel */}
      {memory && (memory.total_fixes > 0 || (memory.tech_stack && memory.tech_stack.primary_language)) && (
        <div className="card memory-card">
          <h3>🧠 Project Memory</h3>
          {memory.tech_stack && memory.tech_stack.primary_language && (
            <div className="memory-tech">
              <span className="memory-badge">{memory.tech_stack.primary_language}</span>
              {(memory.tech_stack.frameworks || []).map((fw, i) => (
                <span key={i} className="memory-badge framework">{fw}</span>
              ))}
            </div>
          )}
          {memory.total_fixes > 0 && (
            <div className="memory-stats">
              <span>📊 {memory.total_fixes} fixes recorded</span>
              <span>✅ {memory.successful_fixes} successful</span>
            </div>
          )}
          {memory.context_notes && memory.context_notes.length > 0 && (
            <div className="memory-notes">
              <p className="notes-label">Recent context:</p>
              {memory.context_notes.slice(-2).map((note, i) => (
                <p key={i} className="note-item">→ {typeof note === 'string' ? note : note.note}</p>
              ))}
            </div>
          )}
          {memory.recent_fixes && memory.recent_fixes.length > 0 && (
            <div className="memory-fixes">
              <p className="fixes-label">Recent fixes:</p>
              {memory.recent_fixes.slice(-2).map((fix, i) => (
                <div key={i} className="fix-item">
                  <span className="fix-type">{fix.error_type}</span>
                  <span className="fix-diag">{(fix.what_fixed || fix.diagnosis || "").slice(0, 60)}...</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Strategy Panel */}
      {strategy && (
        <div className={`card strategy-card ${strategy.type === "memory_match" ? "strategy-memory" : "strategy-fresh"}`}>
          <h3>📋 Agent Strategy</h3>
          <div className="strategy-type">
            {strategy.type === "memory_match" ? (
              <span className="strategy-badge memory">🧠 Memory Match</span>
            ) : (
              <span className="strategy-badge fresh">🔬 Fresh Analysis</span>
            )}
          </div>
          <p className="strategy-msg">{strategy.message}</p>
          <p className="strategy-plan">{strategy.strategy}</p>
          {strategy.past_fix && (
            <div className="past-fix-hint">
              <p className="past-fix-label">Previous fix reference:</p>
              <p className="past-fix-diag">{strategy.past_fix.diagnosis}</p>
              {strategy.past_fix.files_modified && strategy.past_fix.files_modified.length > 0 && (
                <p className="past-fix-files">Files: {strategy.past_fix.files_modified.join(", ")}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Start Debugging Card */}
      <div className="card debug-card">
        <h3>Trigger Autonomous Debugger</h3>
        <p className="card-sub">
          Provide a test command or build script that currently fails. The agent will run it, capture the error traceback, inspect the code, formulate a patch, and verify the fix.
        </p>

        <form onSubmit={handleStart} className="debug-form">
          <label>Failure / Test Command:</label>
          <input
            type="text"
            className="input-field"
            placeholder="e.g. pytest or python main.py"
            value={commandInput}
            onChange={(e) => setCommandInput(e.target.value)}
            disabled={isActive}
          />

          <button
            type="submit"
            className="btn btn-primary btn-launch"
            disabled={isActive}
          >
            {isActive ? "⚡ Debugging in progress..." : "🚀 Launch Agent Loop"}
          </button>
        </form>
      </div>

      {/* Memory Saved Confirmation */}
      {memorySaved && (
        <div className="card memory-saved-card">
          <h3>💾 Fix Saved to Memory</h3>
          <p>{memorySaved.message}</p>
          {memorySaved.fix_summary && (
            <div className="saved-summary">
              <p><strong>Error:</strong> {memorySaved.fix_summary.error_type}</p>
              <p><strong>Fix:</strong> {memorySaved.fix_summary.what_fixed || memorySaved.fix_summary.diagnosis}</p>
              {memorySaved.fix_summary.files_modified && memorySaved.fix_summary.files_modified.length > 0 && (
                <p><strong>Files:</strong> {memorySaved.fix_summary.files_modified.join(", ")}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Active Diff / Patch Preview */}
      {lastDiff && (
        <div className="card diff-card">
          <h3>Last Applied Patch (Git Diff)</h3>
          <pre className="diff-preview">{lastDiff}</pre>
        </div>
      )}
    </div>
  );
}
