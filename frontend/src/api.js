/**
 * api.js — Thin axios wrapper for the Zen backend.
 */
import axios from "axios";

const BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

const api = axios.create({ baseURL: BASE, timeout: 60000 });

export const newSession = () => api.post("/session/new");
export const getProfile = (sessionId) => api.get(`/profile/${sessionId}`);
export const submitCode = (payload) => api.post("/submit", payload);
export const getChallenge = (sessionId) =>
  api.post("/challenge", { session_id: sessionId });
export const getHistory = (sessionId, limit = 20) =>
  api.get(`/history/${sessionId}?limit=${limit}`);
export const resetSession = (sessionId) =>
  api.delete(`/session/${sessionId}`);
