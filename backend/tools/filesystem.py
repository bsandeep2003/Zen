"""
tools/filesystem.py — Filesystem operations for the agent.

Provides tools for inspecting and editing project files:
  - list_files
  - read_file
  - write_file
  - edit_file (search and replace block)
  - delete_file
"""
import os
from pathlib import Path
from typing import Dict, Any, List, Optional


def list_files(project_path: str, subpath: str = "") -> List[Dict[str, Any]]:
    """List directory contents relative to project_path."""
    root = Path(project_path)
    target = (root / subpath).resolve()
    
    # Security check: stay within project
    if not str(target).startswith(str(root.resolve())):
        raise ValueError("Access denied: path outside project root")
        
    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {subpath}")

    items = []
    for entry in target.iterdir():
        if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules", ".venv", "venv", "dist", "build"):
            continue
        rel = str(entry.relative_to(root)).replace("\\", "/")
        items.append({
            "name": entry.name,
            "path": rel,
            "is_dir": entry.is_dir(),
            "size": entry.stat().st_size if entry.is_file() else None,
        })
    return sorted(items, key=lambda x: (not x["is_dir"], x["name"]))


def read_file(project_path: str, rel_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """Read full file or line range from project."""
    root = Path(project_path)
    full_path = (root / rel_path).resolve()
    
    if not str(full_path).startswith(str(root.resolve())):
        raise ValueError("Access denied: path outside project root")
        
    if not full_path.is_file():
        raise FileNotFoundError(f"File not found: {rel_path}")

    content = full_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines(keepends=True)

    if start_line is not None or end_line is not None:
        s = (start_line - 1) if start_line and start_line > 0 else 0
        e = end_line if end_line else len(lines)
        selected = lines[s:e]
        return "".join(selected)
    
    return content


def write_file(project_path: str, rel_path: str, content: str) -> str:
    """Write (create or overwrite) a file in the project."""
    root = Path(project_path)
    full_path = (root / rel_path).resolve()
    
    if not str(full_path).startswith(str(root.resolve())):
        raise ValueError("Access denied: path outside project root")
        
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return f"Successfully wrote {len(content)} bytes to {rel_path}"


def edit_file(project_path: str, rel_path: str, target_content: str, replacement_content: str) -> str:
    """Perform exact target search-and-replace edit in a file."""
    root = Path(project_path)
    full_path = (root / rel_path).resolve()
    
    if not str(full_path).startswith(str(root.resolve())):
        raise ValueError("Access denied: path outside project root")
        
    if not full_path.is_file():
        raise FileNotFoundError(f"File not found: {rel_path}")

    content = full_path.read_text(encoding="utf-8", errors="replace")
    if target_content not in content:
        raise ValueError(f"Target content not found in {rel_path}. Make sure exact block matches.")
        
    count = content.count(target_content)
    if count > 1:
        raise ValueError(f"Target content matched multiple times ({count}) in {rel_path}. Provide more context lines.")

    new_content = content.replace(target_content, replacement_content, 1)
    full_path.write_text(new_content, encoding="utf-8")
    return f"Successfully updated {rel_path}"


def delete_file(project_path: str, rel_path: str) -> str:
    """Delete a file from the project."""
    root = Path(project_path)
    full_path = (root / rel_path).resolve()
    
    if not str(full_path).startswith(str(root.resolve())):
        raise ValueError("Access denied: path outside project root")
        
    if full_path.is_file():
        full_path.unlink()
        return f"Successfully deleted {rel_path}"
    else:
        raise FileNotFoundError(f"File not found: {rel_path}")
