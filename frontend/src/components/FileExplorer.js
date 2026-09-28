import React from "react";

export function FileExplorer({ codebase, activeFile, onSelectFile, onRefresh }) {
  if (!codebase || !codebase.files) {
    return (
      <div className="file-explorer-loading">
        <p>Scanning codebase...</p>
      </div>
    );
  }

  const files = Object.values(codebase.files);

  const getLangBadge = (lang) => {
    switch (lang) {
      case "Python": return "🐍";
      case "JavaScript": return "⚡";
      case "TypeScript": return "📘";
      case "HTML": return "🌐";
      case "CSS": return "🎨";
      case "JSON": return "⚙️";
      default: return "📄";
    }
  };

  return (
    <div className="file-explorer">
      <div className="explorer-header">
        <div className="explorer-title">
          <span className="explorer-icon">📁</span>
          <h3>{codebase.project_name || "Codebase"}</h3>
        </div>
        <button className="icon-btn" onClick={() => onRefresh()} title="Refresh tree">
          🔄
        </button>
      </div>

      <div className="explorer-meta">
        <span className="badge lang-badge">{codebase.primary_language || "Polyglot"}</span>
        <span className="badge count-badge">{codebase.total_files} files</span>
        {codebase.git && codebase.git.branch && (
          <span className="badge git-badge">🌿 {codebase.git.branch}</span>
        )}
      </div>

      <div className="file-list">
        {files.map((file) => {
          const isActive = activeFile === file.relative_path;
          return (
            <div
              key={file.relative_path}
              className={`file-item ${isActive ? "active" : ""} ${file.is_entry_point ? "entry-point" : ""}`}
              onClick={() => onSelectFile(file.relative_path)}
            >
              <span className="file-icon">{getLangBadge(file.language)}</span>
              <span className="file-name" title={file.relative_path}>
                {file.relative_path}
              </span>
              {file.is_entry_point && <span className="entry-tag">entry</span>}
              {file.is_test && <span className="test-tag">test</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
