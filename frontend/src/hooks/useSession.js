/**
 * useSession.js — Persists session_id in localStorage.
 */
import { useState, useEffect } from "react";
import { newSession } from "../api";

export function useSession() {
  const [sessionId, setSessionId] = useState(null);

  useEffect(() => {
    const stored = localStorage.getItem("zen_session_id");
    if (stored) {
      setSessionId(stored);
    } else {
      newSession().then((res) => {
        localStorage.setItem("zen_session_id", res.data.session_id);
        setSessionId(res.data.session_id);
      });
    }
  }, []);

  const clearSession = () => {
    localStorage.removeItem("zen_session_id");
    newSession().then((res) => {
      localStorage.setItem("zen_session_id", res.data.session_id);
      setSessionId(res.data.session_id);
    });
  };

  return { sessionId, clearSession };
}
