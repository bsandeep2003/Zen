import React from "react";

const DIFFICULTY_LABELS = ["", "Beginner", "Elementary", "Intermediate", "Advanced", "Expert"];
const DIFFICULTY_COLORS = ["", "d1", "d2", "d3", "d4", "d5"];

export default function ProfilePanel({ profile, onReset }) {
  if (!profile) {
    return (
      <div className="panel-body">
        <div className="empty-state">Loading profile…</div>
      </div>
    );
  }

  const level = profile.current_difficulty || 1;
  const topMistakes = (profile.mistake_patterns || []).slice(0, 6);

  return (
    <div className="panel-body">
      <div className="profile-card">
        <div className="profile-row">
          <div className="profile-stat">
            <div className="profile-stat-value">{profile.total_submissions ?? 0}</div>
            <div className="profile-stat-label">Submissions</div>
          </div>
          <div className="profile-stat">
            <div className="profile-stat-value">{(profile.avg_score ?? 0).toFixed(0)}</div>
            <div className="profile-stat-label">Avg Score</div>
          </div>
          <div className="profile-stat">
            <div className="profile-stat-value" style={{ color: "var(--text-dim)", fontSize: 13 }}>
              {profile.preferred_language || "python"}
            </div>
            <div className="profile-stat-label">Language</div>
          </div>
        </div>

        {/* Difficulty bar */}
        <div style={{ marginTop: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginBottom: 5 }}>
            <span>Difficulty</span>
            <span style={{ color: "var(--text-dim)" }}>{DIFFICULTY_LABELS[level]}</span>
          </div>
          <div className="difficulty-bar">
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className={`diff-pip${i <= level ? ` active ${DIFFICULTY_COLORS[i]}` : ""}`}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Recurring mistakes */}
      <div className="ai-section">
        <div className="ai-section-title">Recurring Patterns</div>
        {topMistakes.length === 0 ? (
          <div className="empty-state" style={{ padding: "10px 0" }}>
            No patterns yet — submit some code!
          </div>
        ) : (
          <div className="tag-list">
            {topMistakes.map((m) => (
              <span key={m.tag} className="tag">
                {m.tag.replace(/_/g, " ")}
                <span className="tag-count">×{m.count}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Mem0 Memories */}
      <div className="ai-section" style={{ marginTop: 14 }}>
        <div className="ai-section-title">🧠 Mem0 Agent Memories</div>
        {(!profile.memories || profile.memories.length === 0) ? (
          <div className="empty-state" style={{ padding: "6px 0" }}>
            Mem0 is learning your coding habits…
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
            {profile.memories.map((mem, idx) => (
              <div key={idx} style={{
                fontSize: 11,
                background: "var(--surface-3)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                padding: "6px 8px",
                color: "var(--text-dim)",
                lineHeight: 1.4
              }}>
                • {mem}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="divider" />

      <button className="btn-ghost" style={{ width: "100%", fontSize: 12 }} onClick={onReset}>
        ↺ Reset Learning Progress
      </button>
    </div>
  );
}
