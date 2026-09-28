import React, { useState, useRef, useEffect } from "react";

export function TerminalPanel({ logs, onRunCommand }) {
  const [inputCmd, setInputCmd] = useState("");
  const terminalEndRef = useRef(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!inputCmd.trim()) return;
    onRunCommand(inputCmd.trim());
    setInputCmd("");
  };

  return (
    <div className="terminal-panel">
      <div className="terminal-header">
        <span className="terminal-title">🖥️ Execution Environment & Terminal</span>
        <span className="terminal-status">LIVE LOGS</span>
      </div>

      <div className="terminal-output">
        {logs.length === 0 ? (
          <div className="terminal-placeholder">
            Terminal ready. Run a command or start an autonomous debug session.
          </div>
        ) : (
          logs.map((log, index) => (
            <div key={index} className="log-line">
              <pre>{log}</pre>
            </div>
          ))
        )}
        <div ref={terminalEndRef} />
      </div>

      <form className="terminal-input-form" onSubmit={handleSubmit}>
        <span className="prompt-symbol">$</span>
        <input
          type="text"
          className="terminal-input"
          placeholder="Run command in workspace..."
          value={inputCmd}
          onChange={(e) => setInputCmd(e.target.value)}
        />
        <button type="submit" className="btn btn-term-run">Run</button>
      </form>
    </div>
  );
}
