import React from "react";
import { BrowserRouter, Navigate, Route, Routes, useSearchParams } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { AppStateProvider } from "./context/AppStateContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import SignUpPage from "./pages/SignUpPage";
import ChatPage from "./pages/ChatPage";
import MemoryGraphPage from "./pages/MemoryGraphPage";
import WorkspacePage from "./pages/WorkspacePage";
import "./index.css";
import "./styles/zen-agent.css";

function HomeOrWorkspace() {
  const [params] = useSearchParams();
  const workspaceLaunch = ["session", "command", "project", "ws_port"].some(
    (name) => params.has(name) && params.get(name)
  );

  if (workspaceLaunch) {
    return <Navigate to={`/workspace?${params.toString()}`} replace />;
  }

  return (
    <ProtectedRoute>
      <ChatPage />
    </ProtectedRoute>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppStateProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignUpPage />} />
            <Route path="/" element={<HomeOrWorkspace />} />
            <Route
              path="/graph"
              element={
                <ProtectedRoute>
                  <MemoryGraphPage />
                </ProtectedRoute>
              }
            />
            <Route path="/workspace" element={<WorkspacePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AppStateProvider>
    </AuthProvider>
  );
}

export default App;
