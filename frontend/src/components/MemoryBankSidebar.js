import React, { useCallback, useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { fetchMemories } from "../api";

export function MemoryBankSidebar({ open, onClose }) {
  const { user, token, logout } = useAuth();
  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await fetchMemories(token);
      setMemories(data.memories || []);
    } catch {
      setMemories([]);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const initial = (user?.full_name || user?.email || "?").charAt(0).toUpperCase();

  return (
    <>
      <div className={`zen-sidebar-backdrop${open ? " open" : ""}`} onClick={onClose} aria-hidden="true" />
      <aside className={`zen-memory-sidebar${open ? " open" : ""}`} aria-label="Memory Bank">
        <div className="zen-memory-sidebar-header">
          <div className="zen-memory-title">
            <span className="zen-icon-brain" aria-hidden="true">🧠</span>
            Memory Bank
          </div>
          <div className="zen-memory-actions">
            <button type="button" className="zen-icon-btn" onClick={load} title="Refresh" disabled={loading}>
              ↻
            </button>
            <button type="button" className="zen-icon-btn" onClick={onClose} title="Close">
              ×
            </button>
          </div>
        </div>

        <div className="zen-memory-body">
          {loading && <p className="zen-memory-empty">Loading memories…</p>}
          {!loading && memories.length === 0 && (
            <p className="zen-memory-empty">
              No memories yet. Start chatting and I&apos;ll remember important things.
            </p>
          )}
          {!loading &&
            memories.map((m) => (
              <div key={m.id} className="zen-memory-item">
                <span className={`zen-memory-kind ${m.kind}`}>{m.kind}</span>
                <p>{m.text}</p>
              </div>
            ))}
        </div>

        <div className="zen-memory-footer">
          <div className="zen-user-avatar">{initial}</div>
          <div className="zen-user-meta">
            <div className="zen-user-name">{user?.full_name || "User"}</div>
            <div className="zen-user-email">{user?.email}</div>
          </div>
          <button type="button" className="zen-icon-btn" onClick={logout} title="Sign out">
            ⎋
          </button>
        </div>
      </aside>
    </>
  );
}
