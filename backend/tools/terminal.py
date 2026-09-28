"""
tools/terminal.py — Terminal execution tool interface for the agent.

Wraps the terminal executor to be used directly by the agent or LLM tool-calling.
"""
from typing import Dict, Any
from terminal.executor import execute_command


async def run_terminal_command(project_path: str, command: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Run a terminal command in the project directory and return result.
    """
    result = await execute_command(command, cwd=project_path, timeout=timeout)
    return result.to_dict()
