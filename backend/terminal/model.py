"""
terminal/model.py — Data models for the execution environment.

Maintains a live representation of the terminal state including:
- Current and historical command results
- stdout/stderr capture
- Exit codes and durations
- Recent failure tracking
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class CommandResult:
    """Result of a single command execution."""
    command: str
    args: List[str] = field(default_factory=list)
    cwd: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    pid: int = 0
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def error_summary(self) -> str:
        """Extract the most relevant error line from stderr or stdout."""
        text = self.stderr.strip() or self.stdout.strip()
        if not text:
            return ""
        lines = text.strip().splitlines()
        # Return last non-empty line (usually the actual error message)
        for line in reversed(lines):
            stripped = line.strip()
            if stripped:
                return stripped
        return ""

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "args": self.args,
            "cwd": self.cwd,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "pid": self.pid,
            "duration_ms": round(self.duration_ms, 1),
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "timed_out": self.timed_out,
            "error_summary": self.error_summary,
        }


@dataclass
class ExecutionModel:
    """
    Live representation of the execution environment.

    Tracks the current command, full history, and recent failures
    so the agent can correlate errors across multiple runs.
    """
    cwd: str = ""
    current_command: Optional[CommandResult] = None
    command_history: List[CommandResult] = field(default_factory=list)
    max_history: int = 50
    recent_failures: List[CommandResult] = field(default_factory=list)

    def record(self, result: CommandResult):
        """Record a completed command execution."""
        self.current_command = result
        self.command_history.append(result)
        if len(self.command_history) > self.max_history:
            self.command_history = self.command_history[-self.max_history:]
        if not result.success:
            self.recent_failures.append(result)
            if len(self.recent_failures) > 10:
                self.recent_failures = self.recent_failures[-10:]

    def get_last_error(self) -> Optional[CommandResult]:
        """Return the most recent failed command, or None."""
        return self.recent_failures[-1] if self.recent_failures else None

    def get_last_result(self) -> Optional[CommandResult]:
        """Return the most recent command result, or None."""
        return self.command_history[-1] if self.command_history else None

    def clear(self):
        """Reset all state."""
        self.current_command = None
        self.command_history.clear()
        self.recent_failures.clear()

    def add_result(self, result: CommandResult):
        self.record(result)

    def to_summary(self) -> dict:
        last_err = self.get_last_error()
        return {
            "last_error_type": "RuntimeError" if last_err else None,
            "last_error_message": last_err.error_summary if last_err else None,
        }

    def to_dict(self) -> dict:
        return {
            "cwd": self.cwd,
            "current_command": self.current_command.to_dict() if self.current_command else None,
            "command_history": [c.to_dict() for c in self.command_history[-10:]],
            "recent_failures": [c.to_dict() for c in self.recent_failures[-5:]],
            "total_commands": len(self.command_history),
            "total_failures": len(self.recent_failures),
        }

