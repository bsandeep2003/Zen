"""
agent/session.py — In-memory session state holder & active debug manager.

Keeps active CodebaseModel, ExecutionModel, SafetyChecker, and WebSocket broadcasting hooks
for running debug sessions.
"""
import asyncio
from typing import Dict, Any, Optional, List, Callable
from codebase.model import CodebaseModel
from terminal.model import ExecutionModel
from agent.safety import SafetyChecker


class ActiveSession:
    def __init__(
        self,
        session_id: str,
        project_path: str,
        initial_command: str,
        max_attempts: int = 5,
    ):
        self.session_id = session_id
        self.project_path = project_path
        self.initial_command = initial_command
        self.status = "active"  # active | success | failed | escalated
        self.state = "observe"  # observe | diagnose | plan | patch | verify | success | failure
        
        self.codebase = CodebaseModel(project_root=project_path)
        self.execution = ExecutionModel(cwd=project_path)
        self.safety = SafetyChecker(max_attempts=max_attempts)
        
        self.attempts: List[Dict[str, Any]] = []
        self.current_attempt_number = 0
        self.subscribers: List[Callable[[Dict[str, Any]], None]] = []
        self.event_log: List[Dict[str, Any]] = []

    def add_subscriber(self, callback: Callable[[Dict[str, Any]], None]):
        self.subscribers.append(callback)

    def remove_subscriber(self, callback: Callable[[Dict[str, Any]], None]):
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        payload = {
            "session_id": self.session_id,
            "event": event_type,
            "state": self.state,
            "status": self.status,
            "attempt": self.current_attempt_number,
            "data": data,
        }
        self.event_log.append(payload)
        if len(self.event_log) > 250:
            self.event_log = self.event_log[-250:]
        for sub in list(self.subscribers):
            try:
                if asyncio.iscoroutinefunction(sub):
                    await sub(payload)
                else:
                    sub(payload)
            except Exception:
                pass


# Global registry of active in-memory sessions
_active_sessions: Dict[str, ActiveSession] = {}


def get_active_session(session_id: str) -> Optional[ActiveSession]:
    return _active_sessions.get(session_id)


def register_active_session(session: ActiveSession):
    _active_sessions[session.session_id] = session


def unregister_active_session(session_id: str):
    _active_sessions.pop(session_id, None)
