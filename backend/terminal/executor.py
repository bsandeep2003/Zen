"""
terminal/executor.py — Runs commands and captures stdout/stderr/exit code.

This is the core execution engine. Every command the agent runs
goes through here, producing a CommandResult that feeds back into
the debugging loop.
"""
import asyncio
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

from terminal.model import CommandResult, ExecutionModel


def _kill_tree(proc: subprocess.Popen) -> None:
    """Terminate a shell and its children so pipes are released promptly."""
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            # `taskkill /T` is the only way to reach grandchildren via cmd.exe,
            # but it is slow and may be unavailable in confined environments, so
            # it gets a short budget and a fallback.
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=3,
                )
            except Exception:
                pass
            if proc.poll() is None:
                proc.kill()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


class TerminalExecutor:
    """
    Async command executor with full output capture.

    Usage:
        executor = TerminalExecutor(cwd="/path/to/project")
        result = await executor.run("python main.py")
        if not result.success:
            print(result.stderr)
    """

    def __init__(self, cwd: str = "."):
        self.model = ExecutionModel(cwd=cwd)
        self._active_processes: dict[int, asyncio.subprocess.Process] = {}

    async def run(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[dict] = None,
    ) -> CommandResult:
        """
        Execute a shell command and capture its full result.

        Args:
            command: The command string to execute
            cwd: Working directory (defaults to executor's cwd)
            timeout: Max seconds before killing the process
            env: Optional environment variable overrides

        Returns:
            CommandResult with stdout, stderr, exit_code, duration, etc.
        """
        work_dir = cwd or self.model.cwd
        start = time.perf_counter()

        try:
            # Run via subprocess in a worker thread instead of
            # asyncio.create_subprocess_shell. The asyncio variant needs an
            # event-loop pipe (ProactorEventLoop on Windows), which is blocked
            # under confined/sandboxed execution and fails with WinError 5 —
            # breaking both observation and verification. A thread keeps the
            # async interface while using plain, dependable stdio capture.
            def _run() -> CommandResult:
                kwargs = {}
                if sys.platform == "win32":
                    kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    kwargs["start_new_session"] = True

                proc = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=work_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    **kwargs,
                )
                self._active_processes[proc.pid] = proc
                try:
                    stdout_b, stderr_b = proc.communicate(timeout=timeout)
                    rc, timed_out = proc.returncode, False
                except subprocess.TimeoutExpired:
                    # Kill the whole tree: killing just the shell leaves the
                    # real child running and holding the pipes open.
                    _kill_tree(proc)
                    stdout_b, stderr_b = b"", b""
                    try:
                        stdout_b, stderr_b = proc.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    rc, timed_out = 124, True
                finally:
                    self._active_processes.pop(proc.pid, None)

                return CommandResult(
                    command=command,
                    cwd=work_dir,
                    stdout=(stdout_b or b"").decode("utf-8", errors="replace"),
                    stderr=(stderr_b or b"").decode("utf-8", errors="replace"),
                    exit_code=rc,
                    pid=proc.pid,
                    duration_ms=(time.perf_counter() - start) * 1000,
                    timestamp=datetime.now(),
                    timed_out=timed_out,
                )

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, _run)

        except FileNotFoundError:
            elapsed = (time.perf_counter() - start) * 1000
            result = CommandResult(
                command=command,
                cwd=work_dir,
                stderr=f"Command not found: {command.split()[0]}",
                exit_code=127,
                duration_ms=elapsed,
                timestamp=datetime.now(),
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            result = CommandResult(
                command=command,
                cwd=work_dir,
                stderr=f"Execution error: {str(exc)}",
                exit_code=1,
                duration_ms=elapsed,
                timestamp=datetime.now(),
            )

        self.model.record(result)
        return result

    async def kill_process(self, pid: int) -> bool:
        """Kill a running process by PID."""
        proc = self._active_processes.get(pid)
        if proc:
            try:
                proc.kill()
                await proc.wait()
                self._active_processes.pop(pid, None)
                return True
            except Exception:
                pass
        return False

    def get_state(self) -> ExecutionModel:
        """Return the current execution model."""
        return self.model

    def get_history(self) -> list[CommandResult]:
        """Return command history."""
        return self.model.command_history

    def set_cwd(self, cwd: str):
        """Update the working directory."""
        self.model.cwd = cwd


async def execute_command(command: str, cwd: str = ".", timeout: int = 60) -> CommandResult:
    """Convenience function to run a command and return CommandResult."""
    executor = TerminalExecutor(cwd=cwd)
    return await executor.run(command, cwd=cwd, timeout=timeout)

