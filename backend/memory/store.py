"""
memory/store.py — Project-local memory system.

Creates a `.zen/` directory in the target project folder to store:
  - Project map (cached file tree + tech stack info)
  - Fix history (what broke and how it was fixed)
  - Context cache (remembered facts about the project)

This allows the agent to skip redundant analysis on subsequent runs
and apply known fix patterns instantly.
"""
import json
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional


ZEN_DIR = ".zen"
MEMORY_FILE = "memory.json"
FIXES_FILE = "fixes.json"
PROJECT_MAP_FILE = "project_map.json"


def _zen_path(project_path: str) -> Path:
    """Get the .zen/ directory path for a project."""
    return Path(project_path).resolve() / ZEN_DIR


def init_memory(project_path: str) -> Path:
    """Initialize the .zen/ directory in a project. Returns the path."""
    zen = _zen_path(project_path)
    zen.mkdir(exist_ok=True)

    # Create default files if they don't exist
    memory_path = zen / MEMORY_FILE
    if not memory_path.exists():
        memory_path.write_text(json.dumps({
            "project_path": str(Path(project_path).resolve()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tech_stack": {},
            "known_patterns": [],
            "context_notes": [],
        }, indent=2), encoding="utf-8")

    fixes_path = zen / FIXES_FILE
    if not fixes_path.exists():
        fixes_path.write_text(json.dumps([], indent=2), encoding="utf-8")

    project_map_path = zen / PROJECT_MAP_FILE
    if not project_map_path.exists():
        project_map_path.write_text(json.dumps({
            "last_scanned": None,
            "file_tree": [],
            "entry_points": [],
            "config_files": [],
            "primary_language": "",
            "frameworks": [],
        }, indent=2), encoding="utf-8")

    return zen


def has_memory(project_path: str) -> bool:
    """Check if a .zen/ memory directory exists for the project."""
    return (_zen_path(project_path) / MEMORY_FILE).exists()


def load_memory(project_path: str) -> Dict[str, Any]:
    """Load the project memory. Returns empty dict if no memory exists."""
    memory_path = _zen_path(project_path) / MEMORY_FILE
    if not memory_path.exists():
        return {}
    try:
        return json.loads(memory_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_memory(project_path: str, memory: Dict[str, Any]):
    """Save the project memory."""
    zen = _zen_path(project_path)
    zen.mkdir(exist_ok=True)
    memory["updated_at"] = datetime.now(timezone.utc).isoformat()
    (zen / MEMORY_FILE).write_text(
        json.dumps(memory, indent=2, default=str), encoding="utf-8"
    )


# ─── Fix History ─────────────────────────────────────────────────────────────

def compute_error_fingerprint(error_type: str, error_message: str) -> str:
    """Create a fingerprint for an error to match against known fixes."""
    # Normalize: strip line numbers, paths, and dynamic values
    normalized = f"{error_type}:{error_message}".lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def load_fixes(project_path: str) -> List[Dict[str, Any]]:
    """Load all recorded fixes for this project."""
    fixes_path = _zen_path(project_path) / FIXES_FILE
    if not fixes_path.exists():
        return []
    try:
        return json.loads(fixes_path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_fix(project_path: str, fix_record: Dict[str, Any]):
    """Append a new fix to the project's fix history."""
    fixes = load_fixes(project_path)

    fix_record["timestamp"] = datetime.now(timezone.utc).isoformat()
    fix_record["fingerprint"] = compute_error_fingerprint(
        fix_record.get("error_type", ""),
        fix_record.get("error_message", ""),
    )

    fixes.append(fix_record)

    # Keep only last 50 fixes to prevent unbounded growth
    if len(fixes) > 50:
        fixes = fixes[-50:]

    zen = _zen_path(project_path)
    zen.mkdir(exist_ok=True)
    (zen / FIXES_FILE).write_text(
        json.dumps(fixes, indent=2, default=str), encoding="utf-8"
    )


def find_similar_fix(project_path: str, error_type: str, error_message: str) -> Optional[Dict[str, Any]]:
    """
    Search fix history for a similar error. Returns the most recent matching fix or None.
    Uses fingerprint matching for exact matches and fuzzy keyword matching for near-misses.
    """
    fixes = load_fixes(project_path)
    if not fixes:
        return None

    target_fp = compute_error_fingerprint(error_type, error_message)

    # 1. Exact fingerprint match
    for fix in reversed(fixes):
        if fix.get("fingerprint") == target_fp and fix.get("was_successful"):
            return fix

    # 2. Fuzzy match: same error_type + overlapping keywords in message
    error_words = set(error_message.lower().split())
    best_match = None
    best_score = 0

    for fix in reversed(fixes):
        if not fix.get("was_successful"):
            continue
        if fix.get("error_type", "").lower() == error_type.lower():
            fix_words = set(fix.get("error_message", "").lower().split())
            overlap = len(error_words & fix_words)
            if overlap > best_score and overlap >= 2:
                best_score = overlap
                best_match = fix

    return best_match


# ─── Project Map Cache ───────────────────────────────────────────────────────

def load_project_map(project_path: str) -> Dict[str, Any]:
    """Load cached project map."""
    map_path = _zen_path(project_path) / PROJECT_MAP_FILE
    if not map_path.exists():
        return {}
    try:
        return json.loads(map_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_project_map(project_path: str, codebase_summary: Dict[str, Any]):
    """Cache the project map for faster subsequent loads."""
    zen = _zen_path(project_path)
    zen.mkdir(exist_ok=True)

    project_map = {
        "last_scanned": datetime.now(timezone.utc).isoformat(),
        "file_tree": codebase_summary.get("file_tree", ""),
        "entry_points": codebase_summary.get("entry_points", []),
        "config_files": codebase_summary.get("config_files", []),
        "test_files": codebase_summary.get("test_files", []),
        "primary_language": codebase_summary.get("primary_language", ""),
        "frameworks": codebase_summary.get("frameworks", []),
        "total_files": codebase_summary.get("total_files", 0),
        "total_lines": codebase_summary.get("total_lines", 0),
        "dependencies": codebase_summary.get("dependencies", []),
    }

    (zen / PROJECT_MAP_FILE).write_text(
        json.dumps(project_map, indent=2, default=str), encoding="utf-8"
    )


# ─── Tech Stack Memory ──────────────────────────────────────────────────────

def update_tech_stack(project_path: str, language: str, frameworks: List[str]):
    """Update the remembered tech stack for faster future context loading."""
    memory = load_memory(project_path)
    memory["tech_stack"] = {
        "primary_language": language,
        "frameworks": frameworks,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    save_memory(project_path, memory)


def add_context_note(project_path: str, note: str):
    """Add a contextual note about the project (learned from debugging)."""
    memory = load_memory(project_path)
    notes = memory.get("context_notes", [])
    notes.append({
        "note": note,
        "added_at": datetime.now(timezone.utc).isoformat(),
    })
    # Keep last 20 notes
    if len(notes) > 20:
        notes = notes[-20:]
    memory["context_notes"] = notes
    save_memory(project_path, memory)


def get_memory_summary(project_path: str) -> Dict[str, Any]:
    """Get a complete summary of what Zen remembers about this project."""
    memory = load_memory(project_path)
    fixes = load_fixes(project_path)
    project_map = load_project_map(project_path)

    successful_fixes = [f for f in fixes if f.get("was_successful")]

    return {
        "has_memory": has_memory(project_path),
        "project_path": str(Path(project_path).resolve()),
        "tech_stack": memory.get("tech_stack", {}),
        "context_notes": memory.get("context_notes", []),
        "total_fixes": len(fixes),
        "successful_fixes": len(successful_fixes),
        "recent_fixes": successful_fixes[-5:] if successful_fixes else [],
        "project_map": project_map,
        "known_patterns": memory.get("known_patterns", []),
    }
