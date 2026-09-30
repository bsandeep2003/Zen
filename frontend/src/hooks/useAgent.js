import { useState, useEffect, useRef, useCallback } from "react";
import * as api from "../api";
import { useAppState } from "../context/AppStateContext";

export function useAgent(initialProjectPath = ".") {
  const { state, updateWorkspace } = useAppState();
  const workspaceState = state.workspace || {};

  // Parse URL params for CLI-triggered sessions
  const urlParams = new URLSearchParams(window.location.search);
  const urlProject = urlParams.get("project") || initialProjectPath;
  const urlCommand = urlParams.get("command") || "";
  const urlSession = urlParams.get("session") || "";

  // Initialize from persisted state or URL params
  const [projectPath, setProjectPath] = useState(workspaceState.projectPath || urlProject);
  const [codebase, setCo debase] = useState(workspaceState.codebase || null);
  const [activeSession, setActiveSession] = useState(workspaceState.activeSession || urlSession || null);
  const [agentState, setAgentState] = useState(workspaceState.agentState || "idle");
  const [agentStatus, setAgentStatus] = useState(workspaceState.agentStatus || "idle");
  const [logs, setLogs] = useState(workspaceState.logs || []);
  const [attempts, setAttempts] = useState(workspaceState.attempts || []);
  const [activeFile, setActiveFile] = useState(workspaceState.activeFile || null);
  const [fileContent, setFileContent] = useState(workspaceState.fileContent || "");
  const [fileSaving, setFileSaving] = useState(false);
  const [lastDiff, setLastDiff] = useState(workspaceState.lastDiff || "");
  const [memory, setMemory] = useState(workspaceState.memory || null);
  const [strategy, setStrategy] = useState(workspaceState.strategy || null);
  const [memorySaved, setMemorySaved] = useState(workspaceState.memorySaved || null);
  const [explanation, setExplanation] = useState(workspaceState.explanation || null);

  const wsRef = useRef(null);
  const autoStartedRef = useRef(false);

  // Sync all state to AppStateContext whenever it changes
  useEffect(() => {
    updateWorkspace({
      projectPath,
      codebase,
      activeSession,
      agentState,
      agentStatus,
      logs,
      attempts,
      activeFile,
      fileContent,
      fileSaving,
      lastDiff,
      memory,
      strategy,
      memorySaved,
      explanation,
    });
  }, [projectPath, codebase, activeSession, agentState, agentStatus, logs, attempts, activeFile, fileContent, fileSaving, lastDiff, memory, strategy, memorySaved, explanation, updateWorkspace]);

  // Load codebase model
  const refreshCodebase = useCallback(async (path = projectPath) => {
    try {
      const data = await api.getCodebaseModel(path);
      setCodebase(data);
    } catch (err) {
      console.error("Failed to load codebase:", err);
    }
  }, [projectPath]);

  useEffect(() => {
    refreshCodebase(projectPath);
  }, [projectPath, refreshCodebase]);

  // Load project memory on mount
  useEffect(() => {
    async function loadMemory() {
      try {
        const mem = await api.getProjectMemory(projectPath);
        if (mem && mem.has_memory) {
          setMemory(mem);
          if (mem.recent_fixes && mem.recent_fixes.length > 0) {
            const latestFix = mem.recent_fixes[mem.recent_fixes.length - 1];
            if (latestFix.why_failed || latestFix.what_fixed) {
              setExplanation({
                why_failed: latestFix.why_failed,
                what_fixed: latestFix.what_fixed,
                files_modified: latestFix.files_modified || [],
                verified_output: "Verified clean execution",
              });
            }
          }
        }
      } catch (err) {
        // Memory not available yet — that's fine
      }
    }
    loadMemory();
  }, [projectPath]);

  // Open file in viewer
  const openFile = useCallback(async (filePath) => {
    try {
      setActiveFile(filePath);
      const res = await api.readFile(filePath, projectPath);
      setFileContent(res.content);
    } catch (err) {
      console.error(`Failed to read file ${filePath}:`, err);
    }
  }, [projectPath]);

  // Save edited file
  const saveActiveFile = useCallback(async (newContent) => {
    if (!activeFile) return;
    setFileSaving(true);
    try {
      await api.writeFile(activeFile, newContent, projectPath);
      setFileContent(newContent);
      refreshCodebase(projectPath);
    } catch (err) {
      console.error(`Failed to save file ${activeFile}:`, err);
    } finally {
      setFileSaving(false);
    }
  }, [activeFile, projectPath, refreshCodebase]);

  // Connect WebSocket helper
  const connectWebSocket = useCallback((sessionId) => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    const urlParams = new URLSearchParams(window.location.search);
    const wsPort = urlParams.get("ws_port");
    const wsBase = wsPort ? `ws://localhost:${wsPort}` : (process.env.REACT_APP_WS_URL || "ws://localhost:8000");
    const wsUrl = `${wsBase}/ws/agent/${sessionId}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.state) setAgentState(msg.state);
        if (msg.status) setAgentStatus(msg.status);

        if (msg.event === "snapshot") {
          setLogs((prev) => [...prev, `⚡ Connected to session: ${msg.session_id} (Status: ${msg.status})`]);
        } else if (msg.event === "agent_started") {
          setLogs((prev) => [...prev, `🚀 Agent started: ${msg.data?.initial_command || ""}`]);
          setAgentStatus("active");
        } else if (msg.event === "state_change") {
          setLogs((prev) => [...prev, `[STATE] Transitioned to ${msg.state.toUpperCase()} (Attempt #${msg.attempt || 1})`]);
        } else if (msg.event === "tool_call") {
          const tool = msg.data?.tool || "tool";
          const file = msg.data?.file ? ` → ${msg.data.file}` : "";
          setLogs((prev) => [...prev, `🔧 ${tool}${file}`]);
        } else if (msg.event === "llm_error") {
          setLogs((prev) => [...prev, `❌ LLM error: ${msg.data?.error}`]);
        } else if (msg.event === "memory_loaded") {
          setMemory(msg.data);
          if (msg.data.total_fixes > 0) {
            setLogs((prev) => [...prev, `🧠 Memory loaded: ${msg.data.total_fixes} past fixes (${msg.data.successful_fixes} successful)`]);
          } else {
            setLogs((prev) => [...prev, `🧠 ${msg.data.message}`]);
          }
        } else if (msg.event === "strategy") {
          setStrategy(msg.data);
          setLogs((prev) => [...prev, `📋 Strategy: ${msg.data.strategy}`]);
        } else if (msg.event === "patch_applied") {
          setLogs((prev) => [...prev, `[PATCH] Applied change to ${msg.data.file}`]);
          if (activeFile === msg.data.file) openFile(msg.data.file);
          refreshCodebase();
        } else if (msg.event === "patch_failed") {
          setLogs((prev) => [...prev, `[PATCH FAILED] ${msg.data?.file || ""}: ${msg.data?.error || "unknown error"}`]);
        } else if (msg.event === "memory_saved") {
          setMemorySaved(msg.data);
          setLogs((prev) => [...prev, `💾 ${msg.data.message}`]);
          if (msg.data.fix_summary) {
            setExplanation({
              why_failed: msg.data.fix_summary.why_failed,
              what_fixed: msg.data.fix_summary.what_fixed,
              files_modified: msg.data.fix_summary.files_modified || [],
              verified_output: "Exit code 0 (Success)",
            });
          }
        } else if (msg.event === "completed") {
          setLogs((prev) => [...prev, `✅ SUCCESS: ${msg.data.message}`]);
          if (msg.data.patch_diff) setLastDiff(msg.data.patch_diff);
          if (msg.data.why_failed || msg.data.what_fixed) {
            setExplanation({
              why_failed: msg.data.why_failed,
              what_fixed: msg.data.what_fixed,
              files_modified: msg.data.files_modified || [],
              verified_output: msg.data.verified_output || "Exit code 0",
            });
          }
          refreshCodebase();
          api.getProjectMemory(projectPath).then(setMemory).catch(() => {});
        } else if (msg.event === "verification_failed") {
          setLogs((prev) => [...prev, `❌ VERIFICATION FAILED (exit code ${msg.data.exit_code})`]);
          if (msg.data.why_failed) {
            setExplanation((prev) => ({
              ...(prev || {}),
              why_failed: msg.data.why_failed,
            }));
          }
        } else if (msg.event === "failed" || msg.event === "escalated") {
          setLogs((prev) => [...prev, `⚠️ AGENT STOPPED: ${msg.data.error}`]);
        }
      } catch (e) {
        console.error("WS Parse error:", e);
      }
    };

    ws.onclose = () => {
      // ws closed
    };

    wsRef.current = ws;
  }, [projectPath, activeFile, openFile, refreshCodebase]);

  // Load existing session info if session URL parameter is given
  useEffect(() => {
    if (urlSession && !autoStartedRef.current) {
      autoStartedRef.current = true;
      async function attachSession() {
        try {
          const sessionData = await api.getSessionInfo(urlSession);
          if (sessionData) {
            setActiveSession(urlSession);
            setAgentStatus(sessionData.status);
            setAgentState(sessionData.status === "success" ? "success" : "observe");
            if (sessionData.attempts && sessionData.attempts.length > 0) {
              setAttempts(sessionData.attempts);
              const lastAtt = sessionData.attempts[sessionData.attempts.length - 1];
              if (lastAtt.patch_diff) setLastDiff(lastAtt.patch_diff);
              if (lastAtt.why_failed || lastAtt.what_fixed) {
                setExplanation({
                  why_failed: lastAtt.why_failed,
                  what_fixed: lastAtt.what_fixed,
                  files_modified: lastAtt.files_modified || [],
                  verified_output: lastAtt.stdout || "",
                });
              }
              const restoredLogs = [
                `⚡ Attached to session ${urlSession}`,
                `Command: ${sessionData.initial_command}`,
                `Status: ${sessionData.status.toUpperCase()}`,
              ];
              sessionData.attempts.forEach((att) => {
                restoredLogs.push(`[Attempt ${att.attempt_number}] Status: ${att.state}`);
                if (att.diagnosis) restoredLogs.push(`🔍 Diagnosis: ${att.diagnosis}`);
                if (att.stdout) restoredLogs.push(`Output: ${att.stdout}`);
              });
              if (sessionData.status === "success") {
                restoredLogs.push(`✅ SUCCESS: Command resolved!`);
              }
              setLogs(restoredLogs);
            }
            connectWebSocket(urlSession);
            api.getProjectMemory(sessionData.project_path || projectPath).then(setMemory).catch(() => {});
            refreshCodebase(sessionData.project_path || projectPath);
          }
        } catch (err) {
          console.warn("Could not attach to session:", err);
        }
      }
      attachSession();
    }
  }, [urlSession, connectWebSocket, projectPath, refreshCodebase]);

  // Poll session so the dashboard still updates if WebSocket events were missed
  useEffect(() => {
    if (!activeSession) return undefined;
    let stopped = false;
    const tick = async () => {
      try {
        const sessionData = await api.getSessionInfo(activeSession);
        if (stopped) return;
        if (sessionData.status) setAgentStatus(sessionData.status);
        if (sessionData.state) {
          setAgentState(sessionData.status === "success" ? "success" : sessionData.state);
        }
        if (sessionData.attempts && sessionData.attempts.length > 0) {
          setAttempts(sessionData.attempts);
          const lastAtt = sessionData.attempts[sessionData.attempts.length - 1];
          if (lastAtt.patch_diff) setLastDiff(lastAtt.patch_diff);
        }
        if (["success", "failed", "escalated", "stopped"].includes(sessionData.status)) {
          refreshCodebase(sessionData.project_path || projectPath);
          if (sessionData.project_path) {
            api.getProjectMemory(sessionData.project_path).then(setMemory).catch(() => {});
          }
          clearInterval(id);
        }
      } catch (err) {
        // Session endpoint may not be ready yet
      }
    };
    tick();
    const id = setInterval(tick, 1500);
    return () => {
      stopped = true;
      clearInterval(id);
    };
  }, [activeSession, projectPath, refreshCodebase]);

  // Start autonomous debug session
  const startDebugSession = useCallback(async (command) => {
    try {
      setAgentStatus("active");
      setAgentState("observe");
      setStrategy(null);
      setMemorySaved(null);
      setExplanation(null);
      setLogs((prev) => [...prev, `🚀 Starting debug session for command: '${command}'...`]);

      const res = await api.startAgentSession(projectPath, command);
      setActiveSession(res.session_id);
      connectWebSocket(res.session_id);
    } catch (err) {
      console.error("Failed to start debug session:", err);
      setLogs((prev) => [...prev, `❌ Error starting session: ${err.message}`]);
      setAgentStatus("failed");
    }
  }, [projectPath, connectWebSocket]);

  // Auto-start if launched from CLI with ?command= param but NO ?session= param
  useEffect(() => {
    if (urlCommand && !urlSession && !autoStartedRef.current) {
      autoStartedRef.current = true;
      const timer = setTimeout(() => {
        startDebugSession(urlCommand);
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [urlCommand, urlSession, startDebugSession]);

  // Run manual terminal command
  const executeTerminalCmd = useCallback(async (cmd) => {
    setLogs((prev) => [...prev, `$ ${cmd}`]);
    try {
      const res = await api.runCommand(cmd, projectPath);
      if (res.stdout) setLogs((prev) => [...prev, res.stdout]);
      if (res.stderr) setLogs((prev) => [...prev, `[stderr]\n${res.stderr}`]);
      setLogs((prev) => [...prev, `Process exited with code ${res.exit_code}`]);
      return res;
    } catch (err) {
      setLogs((prev) => [...prev, `Execution error: ${err.message}`]);
    }
  }, [projectPath]);

  return {
    projectPath,
    setProjectPath,
    codebase,
    refreshCodebase,
    activeSession,
    agentState,
    agentStatus,
    logs,
    attempts,
    activeFile,
    fileContent,
    setFileContent,
    fileSaving,
    lastDiff,
    memory,
    strategy,
    memorySaved,
    explanation,
    openFile,
    saveActiveFile,
    startDebugSession,
    executeTerminalCmd,
  };
}
