"""
codebase/model.py — Data models for the live codebase representation.

The CodebaseModel is the internal representation of the entire project,
updated incrementally as files change. It holds file metadata, extracted
symbols (functions, classes), imports, dependencies, git state, and
project structure — all queryable by the agent.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class FileInfo:
    """Metadata for a single tracked file."""
    path: str                   # absolute path
    relative_path: str          # relative to project root
    extension: str = ""
    size_bytes: int = 0
    line_count: int = 0
    language: str = ""
    is_test: bool = False
    is_config: bool = False
    is_entry_point: bool = False

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "language": self.language,
            "is_test": self.is_test,
            "is_config": self.is_config,
            "is_entry_point": self.is_entry_point,
        }


@dataclass
class SymbolInfo:
    """A discovered code symbol (function, class, method)."""
    name: str
    kind: str           # "function" | "class" | "method" | "variable" | "import"
    file_path: str      # relative path
    line_number: int
    signature: str = ""  # e.g. "def foo(a, b) -> int:"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "signature": self.signature,
        }


@dataclass
class ImportInfo:
    """A tracked import statement."""
    module: str
    names: List[str] = field(default_factory=list)
    file_path: str = ""
    line_number: int = 0
    is_relative: bool = False

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "names": self.names,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "is_relative": self.is_relative,
        }


@dataclass
class DependencyInfo:
    """A project dependency from requirements.txt or package.json."""
    name: str
    version: str = ""
    source: str = ""    # "requirements.txt" | "package.json"

    def to_dict(self) -> dict:
        return {"name": self.name, "version": self.version, "source": self.source}


@dataclass
class GitState:
    """Current git state snapshot."""
    is_repo: bool = False
    branch: str = ""
    dirty_files: List[str] = field(default_factory=list)
    recent_commits: List[Dict[str, str]] = field(default_factory=list)
    diff: str = ""

    def to_dict(self) -> dict:
        return {
            "is_repo": self.is_repo,
            "branch": self.branch,
            "dirty_files": self.dirty_files[:20],
            "recent_commits": self.recent_commits[:10],
            "diff_preview": self.diff[:2000] if self.diff else "",
        }


@dataclass
class CodebaseModel:
    """
    Live, queryable representation of the entire project.

    Updated incrementally by the scanner — never blindly re-sent
    in its entirety to the LLM. The context builder selects only
    the relevant parts for each request.
    """
    project_root: str = ""
    project_name: str = ""

    # File inventory
    files: Dict[str, FileInfo] = field(default_factory=dict)   # relative_path -> FileInfo

    # Extracted code intelligence
    symbols: List[SymbolInfo] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)
    dependencies: List[DependencyInfo] = field(default_factory=list)

    # Classified file lists
    entry_points: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)

    # Git state
    git: GitState = field(default_factory=GitState)

    # Project metadata
    primary_language: str = ""
    frameworks: List[str] = field(default_factory=list)
    file_tree_snippet: str = ""
    total_files: int = 0
    total_lines: int = 0
    readme_intent: str = ""

    # ── Query methods ───────────────────────────────────────

    def get_file(self, relative_path: str) -> Optional[FileInfo]:
        """Lookup a file by its relative path."""
        return self.files.get(relative_path)

    def get_symbols_in_file(self, relative_path: str) -> List[SymbolInfo]:
        """Return all symbols defined in a specific file."""
        return [s for s in self.symbols if s.file_path == relative_path]

    def find_symbol(self, name: str) -> List[SymbolInfo]:
        """Find all symbols matching a name (case-insensitive)."""
        lower = name.lower()
        return [s for s in self.symbols if lower in s.name.lower()]

    def get_imports_in_file(self, relative_path: str) -> List[ImportInfo]:
        """Return all imports in a specific file."""
        return [i for i in self.imports if i.file_path == relative_path]

    def get_files_importing(self, module: str) -> List[str]:
        """Find files that import a given module."""
        lower = module.lower()
        return list({
            i.file_path for i in self.imports
            if lower in i.module.lower()
        })

    def get_recently_modified(self) -> List[str]:
        """Return files from the git dirty list."""
        return self.git.dirty_files[:10]

    # ── Serialisation ───────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "project_root": self.project_root,
            "project_name": self.project_name,
            "primary_language": self.primary_language,
            "frameworks": self.frameworks,
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "readme_intent": self.readme_intent,
            "file_tree": self.file_tree_snippet,
            "entry_points": self.entry_points,
            "config_files": self.config_files,
            "test_files": self.test_files,
            "dependencies": [d.to_dict() for d in self.dependencies[:20]],
            "git": self.git.to_dict(),
            "files": {k: v.to_dict() for k, v in list(self.files.items())[:100]},
            "symbols": [s.to_dict() for s in self.symbols[:100]],
        }

    def get_summary(self) -> str:
        """Token-efficient summary for LLM context injection (~150-250 tokens)."""
        parts = [f"Project: {self.project_name} | {self.primary_language}"]
        if self.frameworks:
            parts[0] += f" ({', '.join(self.frameworks)})"
        parts[0] += f" | {self.total_files} files, ~{self.total_lines} lines"

        if self.readme_intent:
            parts.append(f"Purpose: {self.readme_intent[:120]}")

        if self.entry_points:
            parts.append(f"Entry points: {', '.join(self.entry_points[:3])}")

        if self.git.is_repo:
            git_line = f"Git: branch={self.git.branch}"
            if self.git.dirty_files:
                git_line += f", {len(self.git.dirty_files)} uncommitted"
            if self.git.recent_commits:
                git_line += f", last='{self.git.recent_commits[0].get('message', '')[:40]}'"
            parts.append(git_line)

        if self.test_files:
            parts.append(f"Tests: {len(self.test_files)} test files")

        return "\n".join(parts)
