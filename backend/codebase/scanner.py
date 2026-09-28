"""
codebase/scanner.py — Project scanner that builds and updates the CodebaseModel.

Evolved from the original project_reader.py. Scans the file tree,
detects the tech stack, reads git state, and populates the CodebaseModel.
Supports incremental updates when individual files change.
"""
import os
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

from codebase.model import (
    CodebaseModel, FileInfo, DependencyInfo, GitState,
)


# ─── Ignore rules ────────────────────────────────────────────────────────────

DEFAULT_IGNORES = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist",
    ".idea", ".vscode", ".DS_Store", "coverage", ".pytest_cache", ".next",
    "target", "vendor", ".mypy_cache", ".tox", "env", ".env",
    "zen.db", "mem0_storage",
}

IGNORED_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".exe", ".dll", ".so", ".dylib", ".bin",
    ".lock", ".log", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".mp4", ".webp", ".zip", ".tar", ".gz", ".woff", ".woff2", ".ttf", ".eot",
}

LANG_MAP = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".rs": "Rust",
    ".go": "Go", ".java": "Java", ".cpp": "C++", ".c": "C",
    ".cs": "C#", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
    ".html": "HTML", ".css": "CSS", ".sql": "SQL", ".sh": "Shell",
}

CONFIG_FILES = {
    "package.json", "requirements.txt", "setup.py", "setup.cfg", "pyproject.toml",
    "Cargo.toml", "go.mod", "Makefile", "Dockerfile", "docker-compose.yml",
    ".env", ".env.example", "tsconfig.json", "webpack.config.js", "vite.config.js",
    ".eslintrc", ".prettierrc", "jest.config.js",
}

ENTRY_POINT_PATTERNS = {
    "main.py", "app.py", "server.py", "index.js", "index.ts",
    "main.go", "main.rs", "Main.java", "manage.py",
}

TEST_PATTERN = re.compile(
    r"(test_.*\.py|.*_test\.py|.*\.test\.[jt]sx?|.*\.spec\.[jt]sx?|^tests/|/__tests__/)",
    re.IGNORECASE,
)


# ─── Git helpers ─────────────────────────────────────────────────────────────

def _run_git(args: List[str], cwd: Path) -> Optional[str]:
    """Run a git command and return stdout, or None on failure."""
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def scan_git_state(root: Path) -> GitState:
    """Collect current git state for the project."""
    if not (root / ".git").exists():
        return GitState(is_repo=False)

    state = GitState(is_repo=True)

    # Branch
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    state.branch = branch or "main"

    # Recent commits
    log_raw = _run_git(["log", "-n", "10", "--pretty=format:%h|%an|%cr|%s"], root)
    if log_raw:
        for line in log_raw.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                state.recent_commits.append({
                    "hash": parts[0], "author": parts[1],
                    "time": parts[2], "message": parts[3],
                })

    # Dirty files
    status_raw = _run_git(["status", "--porcelain"], root)
    if status_raw:
        for line in status_raw.splitlines():
            clean = line.strip()
            if len(clean) > 3:
                state.dirty_files.append(clean[3:].strip())

    # Diff
    diff = _run_git(["diff", "--stat"], root)
    state.diff = diff or ""

    return state


# ─── Dependency detection ────────────────────────────────────────────────────

def _scan_requirements(root: Path) -> List[DependencyInfo]:
    """Parse requirements.txt for Python dependencies."""
    deps = []
    for candidate in [root / "requirements.txt", root / "backend" / "requirements.txt"]:
        if candidate.exists():
            try:
                for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Extract name and version
                        for sep in ["==", ">=", "<=", "~=", "!="]:
                            if sep in line:
                                name, ver = line.split(sep, 1)
                                deps.append(DependencyInfo(name=name.strip(), version=ver.strip(), source="requirements.txt"))
                                break
                        else:
                            deps.append(DependencyInfo(name=line, source="requirements.txt"))
            except Exception:
                pass
            break
    return deps


def _scan_package_json(root: Path) -> List[DependencyInfo]:
    """Parse package.json for Node.js dependencies."""
    deps = []
    for candidate in [root / "package.json", root / "frontend" / "package.json"]:
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8", errors="ignore"))
                for section in ["dependencies", "devDependencies"]:
                    for name, ver in data.get(section, {}).items():
                        deps.append(DependencyInfo(name=name, version=ver, source="package.json"))
            except Exception:
                pass
            break
    return deps


# ─── README ──────────────────────────────────────────────────────────────────

def _extract_readme_intent(root: Path) -> str:
    """Extract project purpose from README."""
    for name in ["README.md", "readme.md", "README.rst"]:
        path = root / name
        if path.exists():
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
                summary = []
                for line in lines[:8]:
                    line = line.strip()
                    if line.startswith("#"):
                        summary.append(line.lstrip("#").strip())
                    elif not line.startswith("!") and not line.startswith("[") and len(line) > 10:
                        summary.append(line)
                    if len(summary) >= 3:
                        break
                return " | ".join(summary)
            except Exception:
                pass
    return ""


# ─── Core scanner ────────────────────────────────────────────────────────────

def scan_project(root_dir: str, target_model: Optional[CodebaseModel] = None) -> CodebaseModel:
    """
    Full scan of a project directory. Returns a populated CodebaseModel.

    This is the main entry point — call once on startup or project change,
    then use update_file() for incremental updates.
    """
    root = Path(root_dir).resolve()
    model = target_model if target_model is not None else CodebaseModel(
        project_root=str(root),
        project_name=root.name,
    )
    model.project_root = str(root)
    model.project_name = root.name

    ext_counts: Dict[str, int] = {}
    tree_lines: List[str] = []
    total_lines = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip ignored directories
        dirnames[:] = [
            d for d in dirnames
            if d not in DEFAULT_IGNORES and not d.startswith(".")
        ]

        rel_dir = os.path.relpath(dirpath, root)
        depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1

        # Build tree snippet (max 3 levels deep)
        if depth <= 2 and len(tree_lines) < 40:
            prefix = "  " * depth
            label = os.path.basename(dirpath) if rel_dir != "." else root.name
            tree_lines.append(f"{prefix}📁 {label}/")

        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if fname in DEFAULT_IGNORES or ext in IGNORED_EXTENSIONS or fname.startswith("."):
                continue

            full_path = Path(dirpath) / fname
            rel_path = os.path.relpath(full_path, root).replace("\\", "/")

            # Determine language
            language = LANG_MAP.get(ext, "")

            # Count lines for source files
            line_count = 0
            size = 0
            try:
                size = full_path.stat().st_size
                if ext in {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".md", ".json", ".go", ".rs", ".java"}:
                    with open(full_path, "rb") as fp:
                        line_count = sum(1 for _ in fp)
                    total_lines += line_count
            except Exception:
                pass

            is_test = bool(TEST_PATTERN.search(rel_path))
            is_config = fname in CONFIG_FILES
            is_entry = fname in ENTRY_POINT_PATTERNS

            file_info = FileInfo(
                path=str(full_path),
                relative_path=rel_path,
                extension=ext,
                size_bytes=size,
                line_count=line_count,
                language=language,
                is_test=is_test,
                is_config=is_config,
                is_entry_point=is_entry,
            )
            model.files[rel_path] = file_info

            if is_test:
                model.test_files.append(rel_path)
            if is_config:
                model.config_files.append(rel_path)
            if is_entry:
                model.entry_points.append(rel_path)

            ext_counts[ext] = ext_counts.get(ext, 0) + 1

            if depth <= 2 and len(tree_lines) < 40:
                prefix = "  " * (depth + 1)
                tree_lines.append(f"{prefix}📄 {fname}")

    # Language stats
    lang_counts: Dict[str, int] = {}
    for ext, count in ext_counts.items():
        lang = LANG_MAP.get(ext)
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + count

    if lang_counts:
        model.primary_language = max(lang_counts.items(), key=lambda x: x[1])[0]

    # Frameworks detection
    frameworks = set()
    deps = _scan_requirements(root) + _scan_package_json(root)
    model.dependencies = deps
    for d in deps:
        name_lower = d.name.lower()
        if name_lower in {"fastapi", "flask", "django", "express", "nest"}:
            frameworks.add(d.name.capitalize())
        elif name_lower in {"react", "vue", "svelte", "next", "angular"}:
            frameworks.add(d.name.capitalize())
        elif name_lower in {"groq", "openai", "langchain"}:
            frameworks.add(d.name)
    model.frameworks = sorted(frameworks)

    # Git
    model.git = scan_git_state(root)

    # README
    model.readme_intent = _extract_readme_intent(root)

    # Metadata
    model.total_files = len(model.files)
    model.total_lines = total_lines
    model.file_tree_snippet = "\n".join(tree_lines[:30])

    return model


def update_file(model: CodebaseModel, rel_path: str) -> CodebaseModel:
    """
    Incrementally update a single file in the model.
    Call this when a file is created, modified, or deleted.
    """
    root = Path(model.project_root)
    full_path = root / rel_path

    if not full_path.exists():
        # File was deleted
        model.files.pop(rel_path, None)
        model.symbols = [s for s in model.symbols if s.file_path != rel_path]
        model.imports = [i for i in model.imports if i.file_path != rel_path]
        model.total_files = len(model.files)
        return model

    # File was created or modified
    ext = full_path.suffix.lower()
    fname = full_path.name
    language = LANG_MAP.get(ext, "")

    line_count = 0
    size = 0
    try:
        size = full_path.stat().st_size
        if ext in {".py", ".js", ".jsx", ".ts", ".tsx"}:
            with open(full_path, "rb") as fp:
                line_count = sum(1 for _ in fp)
    except Exception:
        pass

    file_info = FileInfo(
        path=str(full_path),
        relative_path=rel_path,
        extension=ext,
        size_bytes=size,
        line_count=line_count,
        language=language,
        is_test=bool(TEST_PATTERN.search(rel_path)),
        is_config=fname in CONFIG_FILES,
        is_entry_point=fname in ENTRY_POINT_PATTERNS,
    )
    model.files[rel_path] = file_info
    return model


def update_codebase_model(root_dir: str, model: CodebaseModel, modified_files: Optional[List[str]] = None) -> CodebaseModel:
    """
    Update codebase model after files are modified or patched.
    """
    if modified_files:
        for rel_path in modified_files:
            update_file(model, rel_path)
    else:
        scan_project(root_dir, target_model=model)
    return model

