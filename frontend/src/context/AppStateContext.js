import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const AppStateContext = createContext(null);

const STORAGE_KEY = "zen_app_state";

const buildMemoryGraph = (messages = []) => {
  const nodes = [];
  const edges = [];

  messages.forEach((msg, index) => {
    const text = (msg?.content || "").trim();
    if (!text) return;

    const nodeId = `msg-${index}`;
    nodes.push({
      id: nodeId,
      kind: msg.role === "assistant" ? "fact" : "lesson",
      text,
    });

    if (index > 0) {
      const prev = messages[index - 1];
      if (prev?.content) {
        edges.push({
          id: `edge-${index}`,
          source: `msg-${index - 1}`,
          target: nodeId,
        });
      }
    }
  });

  return {
    nodes,
    edges,
    memory_count: nodes.length,
    connection_count: edges.length,
  };
};

const defaultState = {
  chatMessages: [],
  chatInput: "",
  memoryGraph: {
    nodes: [],
    edges: [],
    memory_count: 0,
    connection_count: 0,
  },
  workspace: {
    projectPath: ".",
    codebase: null,
    activeSession: null,
    agentState: "idle",
    agentStatus: "idle",
    logs: [],
    attempts: [],
    activeFile: null,
    fileContent: "",
    fileSaving: false,
    lastDiff: "",
    memory: null,
    strategy: null,
    memorySaved: null,
    explanation: null,
  },
};

export function AppStateProvider({ children }) {
  const [state, setState] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return defaultState;
      const parsed = JSON.parse(raw);
      const chatMessages = Array.isArray(parsed.chatMessages) ? parsed.chatMessages : [];
      return {
        ...defaultState,
        ...parsed,
        chatMessages,
        memoryGraph: parsed.memoryGraph || buildMemoryGraph(chatMessages),
        workspace: { ...defaultState.workspace, ...(parsed.workspace || {}) },
      };
    } catch {
      return defaultState;
    }
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  const setChatMessages = useCallback((messages) => {
    setState((prev) => ({
      ...prev,
      chatMessages: messages,
      memoryGraph: buildMemoryGraph(messages),
    }));
  }, []);

  const setChatInput = useCallback((value) => {
    setState((prev) => ({ ...prev, chatInput: value }));
  }, []);

  const setMemoryGraph = useCallback((graph) => {
    setState((prev) => ({ ...prev, memoryGraph: graph }));
  }, []);

  const updateWorkspace = useCallback((patch) => {
    setState((prev) => ({
      ...prev,
      workspace: {
        ...prev.workspace,
        ...patch,
      },
    }));
  }, []);

  const resetWorkspace = useCallback(() => {
    setState((prev) => ({
      ...prev,
      workspace: { ...defaultState.workspace },
    }));
  }, []);

  const value = useMemo(
    () => ({
      state,
      setChatMessages,
      setChatInput,
      setMemoryGraph,
      updateWorkspace,
      resetWorkspace,
    }),
    [state, setChatMessages, setChatInput, setMemoryGraph, updateWorkspace, resetWorkspace]
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used within AppStateProvider");
  return ctx;
}

export function clearAppState() {
  localStorage.removeItem(STORAGE_KEY);
}
