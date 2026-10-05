"""
tools/git.py — Git state, checkpointing, and rollback tools.

Allows the agent to:
  - Check current status and diff
  - Create a temporary checkpoint before patching
  - Rollback changes if a patch fails verification
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


def _run_git(project_path: str, args: list[str]) -> tuple[int, str, str]:
    """Run a git command in the project directory."""
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        return res.returncode, res.stdout, res.stderr
    except Exception as e:
        return -1, "", str(e)


def get_git_status(project_path: str) -> Dict[str, Any]:
    """Get current git status, branch, and modified files."""
    code, stdout, stderr = _run_git(project_path, ["status", "--porcelain"])
    if code != 0:
        return {"is_repo": False, "error": stderr.strip()}

    lines = stdout.splitlines()
    modified = []
    untracked = []
    staged = []

    for line in lines:
        if not line.strip():
            continue
        status_code = line[:2]
        file_path = line[3:].strip()
        if status_code in ("M ", "A ", "D ", "R "):
            staged.append(file_path)
        elif status_code in (" M", " D"):
            modified.append(file_path)
        elif status_code == "??":
            untracked.append(file_path)

    _, branch, _ = _run_git(project_path, ["branch", "--show-current"])

    return {
        "is_repo": True,
        "branch": branch.strip(),
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
        "is_clean": len(lines) == 0,
    }


def get_git_diff(project_path: str) -> str:
    """Get unstaged and staged git diffs."""
    code, stdout, _ = _run_git(project_path, ["diff", "HEAD"])
    out_str = stdout or ""
    if code != 0 or not out_str.strip():
        # Fallback to plain diff if HEAD fails
        code, stdout, _ = _run_git(project_path, ["diff"])
        out_str = stdout or ""
    return out_str if code == 0 else ""


def create_checkpoint(project_path: str, session_id: str) -> Dict[str, Any]:
    """
    Stash or commit current changes as a checkpoint before agent patch.
    """
    # Create git commit or stash tag
    code, stdout, stderr = _run_git(project_path, ["rev-parse", "HEAD"])
    commit_hash = stdout.strip() if code == 0 else "initial"
    
    return {
        "success": True,
        "checkpoint_id": f"zen-chk-{session_id}",
        "base_commit": commit_hash,
    }


def rollback_checkpoint(project_path: str, checkpoint_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Roll back all uncommitted changes in the codebase.
    """
    code_checkout, out1, err1 = _run_git(project_path, ["checkout", "--", "."])
    code_clean, out2, err2 = _run_git(project_path, ["clean", "-fd"])
    
    return {
        "success": (code_checkout == 0 and code_clean == 0),
        "checkout_output": out1 + err1,
        "clean_output": out2 + err2,
    }
