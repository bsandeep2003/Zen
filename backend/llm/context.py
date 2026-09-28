"""
llm/context.py — Context Builder for the Debugging Agent.

Formats the CodebaseModel, ExecutionModel, and recent DebugAttempts into a concise,
token-budgeted prompt payload for the LLM.
"""
from typing import Dict, Any, List, Optional
from codebase.model import CodebaseModel
from terminal.model import ExecutionModel


def build_agent_context(
    codebase: CodebaseModel,
    execution: ExecutionModel,
    attempts: List[Dict[str, Any]],
    current_state: str,
) -> Dict[str, Any]:
    """
    Construct selective, high-value context payload for LLM prompt.
    Includes error details, terminal output, git diff, relevant symbol index, and recent attempts.
    """
    # 1. Terminal / Error snippet
    term_summary = execution.to_summary()
    last_cmd = execution.command_history[-1] if execution.command_history else None
    
    # Extract last 50 lines of stderr/stdout if large
    stderr_content = last_cmd.stderr if last_cmd else ""
    stdout_content = last_cmd.stdout if last_cmd else ""
    
    if len(stderr_content.splitlines()) > 50:
        stderr_lines = stderr_content.splitlines()
        stderr_content = "\n".join(stderr_lines[-50:]) + "\n... (truncated)"
        
    if len(stdout_content.splitlines()) > 50:
        stdout_lines = stdout_content.splitlines()
        stdout_content = "\n".join(stdout_lines[-50:]) + "\n... (truncated)"

    # 2. Key Codebase summary
    codebase_summary = codebase.get_summary()

    # 3. Compact attempt history
    compact_attempts = []
    for a in attempts[-3:]:  # Only last 3 attempts
        compact_attempts.append({
            "attempt": a.get("attempt_number"),
            "diagnosis": a.get("diagnosis", "")[:200],
            "patch_files": a.get("files_modified", []),
            "command": a.get("command_run", ""),
            "exit_code": a.get("exit_code"),
            "error_type": a.get("error_type", ""),
        })

    return {
        "state": current_state,
        "project": {
            "root": codebase.project_root,
            "primary_language": codebase.primary_language,
            "frameworks": codebase.frameworks,
            "git_branch": codebase.git.branch,
            "git_diff": codebase.git.diff,
            "recently_modified": codebase.get_recently_modified(),
            "file_count": len(codebase.files),
            "symbol_count": len(codebase.symbols),
            "summary": codebase_summary,
        },
        "execution": {
            "last_command": last_cmd.command if last_cmd else "",
            "exit_code": last_cmd.exit_code if last_cmd else -1,
            "error_type": term_summary.get("last_error_type"),
            "error_message": term_summary.get("last_error_message"),
            "stderr": stderr_content,
            "stdout": stdout_content,
        },
        "symbols": [s.to_dict() for s in codebase.symbols[:30]],  # top symbols
        "past_attempts": compact_attempts,
    }
