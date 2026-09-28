import React from "react";
import { useAgent } from "../hooks/useAgent";
import { FileExplorer } from "../components/FileExplorer";
import { FileViewer } from "../components/FileViewer";
import { TerminalPanel } from "../components/TerminalPanel";
import { AgentPanel } from "../components/AgentPanel";
import { Link } from "react-router-dom";

export default function WorkspacePage() {
  const {
    codebase,
    refreshCodebase,
    agentState,
    agentStatus,
    activeSession,
    logs,
    activeFile,
    fileContent,
    setFileContent,
    fileSaving,
    lastDiff,
    memory,
    strategy,
    memorySaved,
    explanation,
    openFile,
    saveActiveFile,
    startDebugSession,
    executeTerminalCmd,
  } = useAgent(".");

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-brand">
          <Link to="/" className="zen-link-back">
            ← Chat
          </Link>
          <span className="brand-logo">🧘</span>
          <h1>Zen</h1>
          <span className="brand-badge">Autonomous Debugging Agent</span>
        </div>

        {codebase && (
          <div className="header-project-info">
            <span className="info-chip">📂 {codebase.project_name}</span>
            <span className="info-chip">⚡ {codebase.primary_language}</span>
            {codebase.frameworks && codebase.frameworks.length > 0 && (
              <span className="info-chip">🛠️ {codebase.frameworks.join(", ")}</span>
            )}
          </div>
        )}
      </header>

      <main className="workspace">
        <aside className="workspace-left">
          <FileExplorer
            codebase={codebase}
            activeFile={activeFile}
            onSelectFile={openFile}
            onRefresh={refreshCodebase}
          />
        </aside>

        <section className="workspace-center">
          <div className="editor-section">
            <FileViewer
              activeFile={activeFile}
              content={fileContent}
              onChange={(val) => setFileContent(val)}
              onSave={saveActiveFile}
              isSaving={fileSaving}
            />
          </div>

          <div className="terminal-section">
            <TerminalPanel logs={logs} onRunCommand={executeTerminalCmd} />
          </div>
        </section>

        <aside className="workspace-right">
          <AgentPanel
            agentState={agentState}
            agentStatus={agentStatus}
            activeSession={activeSession}
            onStartSession={startDebugSession}
            lastDiff={lastDiff}
            memory={memory}
            strategy={strategy}
            memorySaved={memorySaved}
            explanation={explanation}
          />
        </aside>
      </main>
    </div>
  );
}
