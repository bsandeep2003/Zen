import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const AppStateContext = createContext(null);

const STORAGE_KEY = "zen_app_state";

const defaultState = {
  chatMessages: [],
  chatInput: "",
  workspace: {
    activeFile: null,
    fileContent: "",
    logs: [],
    agentState: "idle",
    agentStatus: "idle",
    lastDiff: "",
    explanation: null,
    memory: null,
    strategy: null,
    memorySaved: null,
  },
};

export function AppStateProvider({ children }) {
  const [state, setState] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return defaultState;
      const parsed = JSON.parse(raw);
      return { ...defaultState, ...parsed, workspace: { ...defaultState.workspace, ...(parsed.workspace || {}) } };
    } catch {
      return defaultState;
    }
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  const setChatMessages = useCallback((messages) => {
    setState((prev) => ({ ...prev, chatMessages: messages }));
  }, []);

  const setChatInput = useCallback((value) => {
    setState((prev) => ({ ...prev, chatInput: value }));
  }, []);

  const updateWorkspace = useCallback((patch) => {
    setState((prev) => ({
      ...prev,
      workspace: { ...prev.workspace, ...patch },
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
      updateWorkspace,
      resetWorkspace,
    }),
    [state, setChatMessages, setChatInput, updateWorkspace, resetWorkspace]
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
