/**
 * api.js — API client for Zen Autonomous Debugging Agent.
 */
function resolveApiBase() {
  if (typeof window !== "undefined") {
    const port = new URLSearchParams(window.location.search).get("ws_port");
    if (port) return `http://localhost:${port}`;
  }
  return process.env.REACT_APP_API_URL || "http://localhost:8000";
}

const API_BASE = resolveApiBase();

async function parseError(res) {
  const text = await res.text();
  try {
    const data = JSON.parse(text);
    return data.detail || text;
  } catch {
    return text || res.statusText;
  }
}

function authHeaders(token) {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

// ─── Auth ───────────────────────────────────────────────────────────────────

export const register = async (fullName, email, password) => {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ full_name: fullName, email, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
};

export const login = async (email, password) => {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
};

export const fetchMe = async (token) => {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
};

// ─── Zen chat & memory ──────────────────────────────────────────────────────

export const sendChatMessage = async (token, message, history = []) => {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
};

export const fetchMemories = async (token) => {
  const res = await fetch(`${API_BASE}/chat/memories`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
};

export const fetchMemoryGraph = async (token) => {
  const res = await fetch(`${API_BASE}/chat/graph`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
};

// ─── Debug agent workspace ────────────────────────────────────────────────────

export const startAgentSession = async (projectPath, initialCommand, maxAttempts = 5) => {
  const res = await fetch(`${API_BASE}/agent/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_path: projectPath,
      initial_command: initialCommand,
      max_attempts: maxAttempts,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const getSessionInfo = async (sessionId) => {
  const res = await fetch(`${API_BASE}/agent/session/${sessionId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const runCommand = async (command, projectPath = ".") => {
  const res = await fetch(`${API_BASE}/agent/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, project_path: projectPath }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const getCodebaseModel = async (projectPath = ".") => {
  const res = await fetch(`${API_BASE}/agent/codebase?project_path=${encodeURIComponent(projectPath)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const readFile = async (filePath, projectPath = ".") => {
  const res = await fetch(`${API_BASE}/agent/file/read`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_path: filePath, project_path: projectPath }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const writeFile = async (filePath, content, projectPath = ".") => {
  const res = await fetch(`${API_BASE}/agent/file/write`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_path: filePath, content, project_path: projectPath }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const stopAgentSession = async (sessionId) => {
  const res = await fetch(`${API_BASE}/agent/stop/${sessionId}`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const getProjectMemory = async (projectPath = ".") => {
  const res = await fetch(`${API_BASE}/agent/memory?project_path=${encodeURIComponent(projectPath)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

export const getProjectFixes = async (projectPath = ".") => {
  const res = await fetch(`${API_BASE}/agent/memory/fixes?project_path=${encodeURIComponent(projectPath)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};
