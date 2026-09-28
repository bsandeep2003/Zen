import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { fetchMemoryGraph } from "../api";

export default function MemoryGraphPage() {
  const { token } = useAuth();
  const [graph, setGraph] = useState({
    nodes: [],
    edges: [],
    memory_count: 0,
    connection_count: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchMemoryGraph(token);
        if (!cancelled) setGraph(data);
      } catch {
        if (!cancelled) {
          setGraph({ nodes: [], edges: [], memory_count: 0, connection_count: 0 });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const empty = !loading && graph.memory_count === 0;

  return (
    <div className="zen-graph-app">
      <header className="zen-graph-header">
        <div className="zen-graph-brand">
          <span className="zen-graph-logo">◆</span>
          Zen Memory Graph
        </div>
        <div className="zen-graph-stats">
          <span>{graph.memory_count} memories</span>
          <span>{graph.connection_count} connections</span>
          <span className="zen-live">
            <span className="zen-live-dot" /> Live
          </span>
        </div>
        <div className="zen-graph-legend">
          <span><i className="dot fact" /> Fact</span>
          <span><i className="dot lesson" /> Lesson</span>
          <Link to="/" className="zen-graph-back">
            ← Chat
          </Link>
        </div>
      </header>

      <main className="zen-graph-canvas">
        {loading && <p className="zen-graph-empty">Loading graph…</p>}
        {empty && (
          <div className="zen-graph-empty-state">
            <h2>No memories yet</h2>
            <p>Start chatting with Zen to build your memory graph</p>
            <Link to="/" className="zen-btn-primary zen-graph-cta">
              Open chat
            </Link>
          </div>
        )}
        {!loading && !empty && (
          <div className="zen-graph-nodes">
            {graph.nodes.map((node, index) => (
              <div
                key={node.id}
                className={`zen-graph-node ${node.kind}`}
                style={{
                  left: `${12 + (index % 5) * 17}%`,
                  top: `${15 + Math.floor(index / 5) * 22}%`,
                }}
              >
                <span className="zen-graph-node-kind">{node.kind}</span>
                <p>{node.text}</p>
              </div>
            ))}
            <svg className="zen-graph-lines" aria-hidden="true">
              {graph.edges.map((e, i) => {
                const si = graph.nodes.findIndex((n) => n.id === e.source);
                const ti = graph.nodes.findIndex((n) => n.id === e.target);
                if (si < 0 || ti < 0) return null;
                const x1 = 12 + (si % 5) * 17 + 8;
                const y1 = 15 + Math.floor(si / 5) * 22 + 6;
                const x2 = 12 + (ti % 5) * 17 + 8;
                const y2 = 15 + Math.floor(ti / 5) * 22 + 6;
                return (
                  <line key={e.id || i} x1={`${x1}%`} y1={`${y1}%`} x2={`${x2}%`} y2={`${y2}%`} />
                );
              })}
            </svg>
          </div>
        )}
      </main>
    </div>
  );
}
