import React, { useRef, useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { useAuth } from "../context/AuthContext";
import { useAppState } from "../context/AppStateContext";
import { sendChatMessage, saveMemory } from "../api";
import { MemoryBankSidebar } from "../components/MemoryBankSidebar";

const QUICK_PROMPTS = [
  "What can you remember?",
  "Tell me about yourself",
  "How does your memory work?",
];

export default function ChatPage() {
  const { token } = useAuth();
  const { state, setChatMessages, setChatInput } = useAppState();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const listRef = useRef(null);

  const messages = useMemo(() => state.chatMessages || [], [state.chatMessages]);
  const input = useMemo(() => state.chatInput || "", [state.chatInput]);

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    if (listRef.current) {
      setTimeout(() => {
        listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
      }, 100);
    }
  }, [messages]);

  // Persist chat messages to backend whenever they change
  useEffect(() => {
    if (messages.length > 0 && token) {
      const userMessages = messages.filter((m) => m.role === "user").map((m) => m.content);
      if (userMessages.length > 0) {
        saveMemory(token, { conversations: userMessages }).catch((err) => {
          console.warn("Failed to save memory:", err);
        });
      }
    }
  }, [messages, token]);

  const send = async (text) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const userMsg = { role: "user", content: trimmed };
    const nextHistory = [...messages, userMsg];
    setChatMessages(nextHistory);
    setChatInput("");
    setLoading(true);

    try {
      const history = messages.map(({ role, content }) => ({ role, content }));
      const { reply } = await sendChatMessage(token, trimmed, history);
      setChatMessages([...nextHistory, { role: "assistant", content: reply }]);
    } catch (err) {
      setChatMessages([
        ...nextHistory,
        { role: "assistant", content: `Sorry — ${err.message || "something went wrong"}.` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const hasChat = messages.length > 0;
  const modelBadge = process.env.REACT_APP_MODEL_BADGE || "Gemini + mem0";

  return (
    <div className="zen-chat-app">
      <MemoryBankSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <header className="zen-topbar">
        <div className="zen-topbar-left">
          <button type="button" className="zen-icon-btn" onClick={() => setSidebarOpen(true)} aria-label="Menu">
            ☰
          </button>
          <span className="zen-star-logo">✦</span>
          <span className="zen-topbar-brand">Zen Agent</span>
        </div>
        <Link to="/graph" className="zen-graph-btn">
          <span aria-hidden="true">◉</span> Graph
        </Link>
        <div className="zen-topbar-right">
          <span className="zen-model-pill">{modelBadge}</span>
          <Link to="/workspace" className="zen-workspace-link" title="Debug workspace">
            Workspace
          </Link>
        </div>
      </header>

      <main className={`zen-chat-main${hasChat ? " has-messages" : ""}`} ref={listRef}>
        {!hasChat && (
          <div className="zen-hero">
            <div className="zen-hero-brain">🧠</div>
            <h1>Hello, I&apos;m Zen</h1>
            <p>A self-learning AI agent. I remember our conversations and get better over time.</p>
            <div className="zen-quick-prompts">
              {QUICK_PROMPTS.map((q) => (
                <button key={q} type="button" onClick={() => send(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {hasChat && (
          <div className="zen-message-list">
            {messages.map((m, i) => (
              <div key={i} className={`zen-message ${m.role}`}>
                {m.role === "assistant" ? (
                  <ReactMarkdown>{m.content}</ReactMarkdown>
                ) : (
                  <p>{m.content}</p>
                )}
              </div>
            ))}
            {loading && (
              <div className="zen-message assistant zen-typing">
                <span />
                <span />
                <span />
              </div>
            )}
          </div>
        )}
      </main>

      <footer className="zen-composer-wrap">
        <form
          className="zen-composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            type="text"
            placeholder="Message Zen…"
            value={input}
            onChange={(e) => setChatInput(e.target.value)}
            disabled={loading}
          />
          <button type="submit" disabled={loading || !input.trim()} aria-label="Send">
            ➤
          </button>
        </form>
        <p className="zen-composer-note">Zen learns from every conversation via mem0 memory</p>
      </footer>
    </div>
  );
}
