"""
codebase/search.py — Code search across the project.

Provides grep-like search and symbol lookup capabilities
for the agent to find relevant code quickly.
"""
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from codebase.model import CodebaseModel, SymbolInfo


@dataclass
class SearchResult:
    """A single search match."""
    file_path: str          # relative path
    line_number: int
    line_content: str
    match_text: str = ""

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "line_content": self.line_content.strip(),
            "match_text": self.match_text,
        }


def search_code(
    model: CodebaseModel,
    query: str,
    max_results: int = 20,
    file_pattern: Optional[str] = None,
    case_sensitive: bool = False,
) -> List[SearchResult]:
    """
    Search for a text pattern across all source files in the project.

    Args:
        model: The current CodebaseModel
        query: Text or regex pattern to search for
        max_results: Maximum number of matches to return
        file_pattern: Optional glob filter (e.g. "*.py")
        case_sensitive: Whether the search is case-sensitive

    Returns:
        List of SearchResult with file, line number, and content
    """
    results: List[SearchResult] = []
    flags = 0 if case_sensitive else re.IGNORECASE

    try:
        pattern = re.compile(re.escape(query), flags)
    except re.error:
        return results

    searchable_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".html", ".css",
                       ".go", ".rs", ".java", ".md", ".yml", ".yaml", ".toml", ".cfg",
                       ".sh", ".bat", ".sql", ".rb", ".php"}

    for rel_path, file_info in model.files.items():
        if len(results) >= max_results:
            break

        # Filter by extension
        if file_info.extension not in searchable_exts:
            continue

        # Filter by file pattern
        if file_pattern:
            from fnmatch import fnmatch
            if not fnmatch(rel_path, file_pattern):
                continue

        # Skip large files
        if file_info.size_bytes > 500_000:
            continue

        try:
            content = Path(file_info.path).read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(content.splitlines(), 1):
                if len(results) >= max_results:
                    break
                match = pattern.search(line)
                if match:
                    results.append(SearchResult(
                        file_path=rel_path,
                        line_number=i,
                        line_content=line,
                        match_text=match.group(),
                    ))
        except Exception:
            continue

    return results


def find_symbol(model: CodebaseModel, name: str) -> List[Dict[str, Any]]:
    """
    Find all symbols matching a name in the indexed codebase.

    Returns symbol info with surrounding context lines.
    """
    matches = model.find_symbol(name)
    results = []

    for sym in matches[:10]:
        entry = sym.to_dict()

        # Try to add a few lines of surrounding context
        file_info = model.get_file(sym.file_path)
        if file_info:
            try:
                content = Path(file_info.path).read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
                start = max(0, sym.line_number - 2)
                end = min(len(lines), sym.line_number + 5)
                entry["context"] = "\n".join(lines[start:end])
            except Exception:
                entry["context"] = ""

        results.append(entry)

    return results


def find_files_related_to_error(
    model: CodebaseModel,
    error_text: str,
) -> List[str]:
    """
    Given an error message (e.g. a traceback), find which project files
    are likely involved by matching filenames and symbols mentioned in
    the error text.
    """
    related: List[str] = []

    # 1. Look for explicit file paths in the error
    # Match patterns like: File "path/to/file.py", line 42
    file_refs = re.findall(r'["\']?([^"\'<>\s]+\.(py|js|ts|jsx|tsx))["\']?', error_text)
    for ref, _ext in file_refs:
        # Normalise
        ref_norm = ref.replace("\\", "/")
        for rel_path in model.files:
            if rel_path.endswith(ref_norm) or ref_norm.endswith(rel_path):
                if rel_path not in related:
                    related.append(rel_path)

    # 2. Look for module names (e.g. "No module named 'foo'")
    module_refs = re.findall(r"No module named '(\w+)'", error_text)
    module_refs += re.findall(r"ModuleNotFoundError.*?'(\w+)'", error_text)
    module_refs += re.findall(r"ImportError.*?'(\w+)'", error_text)
    for mod in module_refs:
        # Check if it's a local module
        for rel_path in model.files:
            stem = Path(rel_path).stem
            if stem == mod:
                if rel_path not in related:
                    related.append(rel_path)

    # 3. Look for symbol names mentioned in errors
    # e.g. "TypeError: foo() takes 2 arguments"
    symbol_refs = re.findall(r"(\w+)\(\)", error_text)
    symbol_refs += re.findall(r"has no attribute '(\w+)'", error_text)
    symbol_refs += re.findall(r"NameError.*?'(\w+)'", error_text)
    for sym_name in symbol_refs:
        matches = model.find_symbol(sym_name)
        for m in matches[:3]:
            if m.file_path not in related:
                related.append(m.file_path)

    # 4. Always include entry points
    for ep in model.entry_points:
        if ep not in related:
            related.append(ep)

    return related[:15]


def correlation_search(project_path: str, error_text: str, model: CodebaseModel) -> List[Dict[str, Any]]:
    """
    Correlate an error traceback with codebase files and return list of file dicts.
    """
    rel_paths = find_files_related_to_error(model, error_text)
    correlated = []
    for rel_path in rel_paths:
        file_info = model.get_file(rel_path)
        if file_info:
            correlated.append({
                "path": rel_path,
                "language": file_info.language,
                "size_bytes": file_info.size_bytes,
                "symbols": [s.to_dict() for s in model.symbols if s.file_path == rel_path],
            })
    return correlated

