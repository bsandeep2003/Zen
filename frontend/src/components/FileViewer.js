import React from "react";
import Editor from "@monaco-editor/react";

export function FileViewer({ activeFile, content, onChange, onSave, isSaving }) {
  if (!activeFile) {
    return (
      <div className="file-viewer-empty">
        <div className="empty-state-content">
          <span className="empty-icon">💻</span>
          <h3>No File Selected</h3>
          <p>Select a file from the explorer on the left to view or edit code.</p>
        </div>
      </div>
    );
  }

  const getLanguage = (path) => {
    if (path.endsWith(".py")) return "python";
    if (path.endsWith(".js") || path.endsWith(".jsx")) return "javascript";
    if (path.endsWith(".ts") || path.endsWith(".tsx")) return "typescript";
    if (path.endsWith(".json")) return "json";
    if (path.endsWith(".html")) return "html";
    if (path.endsWith(".css")) return "css";
    return "plaintext";
  };

  return (
    <div className="file-viewer">
      <div className="viewer-header">
        <div className="viewer-title">
          <span className="file-path">{activeFile}</span>
        </div>
        <button
          className="btn btn-save"
          onClick={() => onSave(content)}
          disabled={isSaving}
        >
          {isSaving ? "Saving..." : "💾 Save File"}
        </button>
      </div>

      <div className="editor-container">
        <Editor
          height="100%"
          language={getLanguage(activeFile)}
          value={content}
          theme="vs-dark"
          onChange={(val) => onChange(val || "")}
          options={{
            fontSize: 14,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            automaticLayout: true,
            lineNumbers: "on",
            wordWrap: "on",
          }}
        />
      </div>
    </div>
  );
}
