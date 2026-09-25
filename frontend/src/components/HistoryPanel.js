import React from "react";

export default function HistoryPanel({ history }) {
  if (!history || history.length === 0) {
    return (
      <div className="panel-body">
        <div className="empty-state">No submissions yet.</div>
      </div>
    );
  }

  const scoreClass = (s) => s >= 75 ? "score-high" : s >= 45 ? "score-mid" : "score-low";

  return (
    <div className="panel-body">
      {history.map((item) => (
        <div key={item.id} className="history-item">
          <div className="history-item-top">
            <span className="history-lang">{item.language}</span>
            <span className={`history-score ${scoreClass(item.score)}`}>
              {Math.round(item.score)}
            </span>
          </div>
          <div className="history-task">
            {item.task_description || "(no task)"}
          </div>
          {item.mistake_tags?.filter(Boolean).length > 0 && (
            <div className="tag-list" style={{ marginTop: 5 }}>
              {item.mistake_tags.filter(Boolean).slice(0, 3).map((t) => (
                <span key={t} className="tag" style={{ fontSize: 10 }}>
                  {t.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
