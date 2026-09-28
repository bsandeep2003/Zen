"""
terminal/executor.py — Runs commands and captures stdout/stderr/exit code.

This is the core execution engine. Every command the agent runs
goes through here, producing a CommandResult that feeds back into
the debugging loop.
"""
import asyncio
import time
import shlex
import sys
from datetime import datetime
from typing import Optional

from terminal.model import CommandResult, ExecutionModel


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
            # Use shell=True on Windows for proper command resolution
            is_win = sys.platform == "win32"
            if is_win:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=work_dir,
                    env=env,
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=work_dir,
                    env=env,
                )

            self._active_processes[process.pid] = process

            timed_out = False
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                timed_out = True
                process.kill()
                stdout_bytes, stderr_bytes = await process.communicate()

            elapsed = (time.perf_counter() - start) * 1000  # ms

            result = CommandResult(
                command=command,
                cwd=work_dir,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                exit_code=process.returncode or 0,
                pid=process.pid,
                duration_ms=elapsed,
                timestamp=datetime.now(),
                timed_out=timed_out,
            )

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
        finally:
            # Clean up process tracking
            if "process" in dir() and hasattr(process, "pid"):
                self._active_processes.pop(process.pid, None)

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

