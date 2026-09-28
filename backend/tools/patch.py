"""
tools/patch.py — Code patch tool for targeted codebase modifications.

Supports:
  - Multi-file search-and-replace patches
  - Unified diff format application
"""
import re
from pathlib import Path
from typing import Dict, Any, List
from tools.filesystem import edit_file, write_file


def apply_patch(project_path: str, file_path: str, search: str, replace: str) -> Dict[str, Any]:
    """
    Apply targeted search-and-replace edit to a file.
    
    Returns structured result with success status, diff preview, and modified path.
    """
    try:
        msg = edit_file(project_path, file_path, search, replace)
        return {
            "success": True,
            "message": msg,
            "file_path": file_path,
            "search_snippet": search[:100],
            "replace_snippet": replace[:100],
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "file_path": file_path,
        }


def apply_multi_patch(project_path: str, patches: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Apply multiple file patches in sequence.
    Each patch dict must contain: 'file_path', 'search', 'replace'.
    """
    results = []
    modified_files = []
    all_success = True

    for p in patches:
        res = apply_patch(project_path, p["file_path"], p["search"], p["replace"])
        results.append(res)
        if res["success"]:
            modified_files.append(p["file_path"])
        else:
            all_success = False

    return {
        "success": all_success,
        "modified_files": modified_files,
        "details": results,
    }
