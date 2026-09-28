"""
project_reader.py — Layer 1: Project Awareness Engine for Zen Agent.

Extracts deep project context:
  1. Directory hierarchy & file inventory (respects .gitignore / common ignores)
  2. Tech stack & dependencies (Python, Node.js/React, Rust, Go, etc.)
  3. Git history & velocity (recent commits, dirty files, active hotspots)
  4. Test coverage heuristics & test gaps (untested source files vs tests)
  5. Project purpose & README intent
  6. Token-efficient LLM context generator (~150-250 tokens)
"""

import os
import re
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any


# ─── Default Ignored Directories & Files ─────────────────────────────────────
DEFAULT_IGNORES = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist",
    ".idea", ".vscode", ".DS_Store", "coverage", ".pytest_cache", ".next",
    "mem0_storage", "zen.db", "target", "vendor", ".mypy_cache"
}

IGNORED_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".exe", ".dll", ".so", ".dylib", ".bin",
    ".lock", ".log", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".mp4", ".webp", ".zip", ".tar", ".gz", ".woff", ".woff2", ".ttf", ".eot"
}


@dataclass
class StackInfo:
    primary_language: str = "unknown"
    languages: Dict[str, int] = field(default_factory=dict)  # lang -> file count
    frameworks: List[str] = field(default_factory=list)
    package_managers: List[str] = field(default_factory=list)
    key_dependencies: List[str] = field(default_factory=list)
    test_frameworks: List[str] = field(default_factory=list)


@dataclass
class GitActivity:
    is_git_repo: bool = False
    branch: str = ""
    recent_commits: List[Dict[str, str]] = field(default_factory=list)  # hash, date, msg, author
    uncommitted_files: List[str] = field(default_factory=list)
    hotspot_files: List[Dict[str, Any]] = field(default_factory=list)  # file -> modification count
    commits_last_7_days: int = 0


@dataclass
class TestSurface:
    test_files: List[str] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)
    untested_sources: List[str] = field(default_factory=list)
    has_tests: bool = False


@dataclass
class ProjectSummary:
    root_path: str
    project_name: str
    readme_intent: str = ""
    total_files: int = 0
    total_lines: int = 0
    stack: StackInfo = field(default_factory=StackInfo)
    git: GitActivity = field(default_factory=GitActivity)
    tests: TestSurface = field(default_factory=TestSurface)
    file_tree_snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Git Inspection ──────────────────────────────────────────────────────────

def _run_git(args: List[str], cwd: Path) -> Optional[str]:
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


def get_git_activity(root: Path) -> GitActivity:
    git_dir = root / ".git"
    if not git_dir.exists():
        return GitActivity(is_git_repo=False)

    activity = GitActivity(is_git_repo=True)

    # Current branch
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    activity.branch = branch or "main"

    # Recent commits (last 15)
    log_raw = _run_git(
        ["log", "-n", "15", "--pretty=format:%h|%an|%cr|%s"],
        root
    )
    if log_raw:
        commits = []
        for line in log_raw.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "time": parts[2],
                    "message": parts[3]
                })
        activity.recent_commits = commits

    # Commits in last 7 days
    count_7d = _run_git(["rev-list", "--count", "--since=7.days.ago", "HEAD"], root)
    if count_7d and count_7d.isdigit():
        activity.commits_last_7_days = int(count_7d)

    # Uncommitted / modified files
    status_raw = _run_git(["status", "--porcelain"], root)
    if status_raw:
        uncommitted = []
        for line in status_raw.splitlines():
            clean = line.strip()
            if len(clean) > 3:
                uncommitted.append(clean[3:].strip())
        activity.uncommitted_files = uncommitted[:20]

    # Hotspot files (most edited in last 30 commits)
    diff_stat = _run_git(["log", "-n", "30", "--name-only", "--pretty=format:"], root)
    if diff_stat:
        file_counts: Dict[str, int] = {}
        for f in diff_stat.splitlines():
            f = f.strip()
            if f and not any(part in f for part in DEFAULT_IGNORES):
                file_counts[f] = file_counts.get(f, 0) + 1
        
        sorted_hotspots = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        activity.hotspot_files = [{"file": k, "changes": v} for k, v in sorted_hotspots]

    return activity


# ─── Stack & Dependency Detection ────────────────────────────────────────────

def detect_stack(root: Path, file_extensions: Dict[str, int]) -> StackInfo:
    stack = StackInfo()
    
    # Map file extensions to languages
    lang_map = {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "React (JSX)",
        ".ts": "TypeScript",
        ".tsx": "React (TSX)",
        ".rs": "Rust",
        ".go": "Go",
        ".java": "Java",
        ".cpp": "C++",
        ".c": "C",
        ".cs": "C#",
        ".html": "HTML",
        ".css": "CSS",
        ".sql": "SQL",
    }
    
    languages: Dict[str, int] = {}
    for ext, count in file_extensions.items():
        lang = lang_map.get(ext)
        if lang:
            languages[lang] = languages.get(lang, 0) + count
    
    stack.languages = languages
    if languages:
        stack.primary_language = max(languages.items(), key=lambda x: x[1])[0]

    deps = set()
    frameworks = set()
    test_frameworks = set()
    pms = set()

    # Python inspection
    req_file = root / "backend" / "requirements.txt"
    if not req_file.exists():
        req_file = root / "requirements.txt"
    if req_file.exists():
        pms.add("pip")
        try:
            content = req_file.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                line = line.strip().split("==")[0].split(">=")[0].split("<=")[0].strip().lower()
                if line and not line.startswith("#"):
                    deps.add(line)
                    if line in ["fastapi", "flask", "django", "tornado", "litestar"]:
                        frameworks.add(line.capitalize())
                    if line in ["pytest", "unittest", "hypothesis"]:
                        test_frameworks.add(line)
                    if line in ["mem0ai", "groq", "openai", "langchain", "llama-index"]:
                        frameworks.add(line)
        except Exception:
            pass

    # Node.js inspection
    pkg_file = root / "frontend" / "package.json"
    if not pkg_file.exists():
        pkg_file = root / "package.json"
    if pkg_file.exists():
        pms.add("npm/yarn")
        try:
            pkg_data = json.loads(pkg_file.read_text(encoding="utf-8", errors="ignore"))
            all_deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
            for dep in all_deps.keys():
                deps.add(dep)
                if dep in ["react", "next", "vue", "svelte", "express", "nest"]:
                    frameworks.add(dep.capitalize())
                if dep in ["jest", "vitest", "mocha", "@testing-library/react", "cypress", "playwright"]:
                    test_frameworks.add(dep)
        except Exception:
            pass

    stack.key_dependencies = sorted(list(deps))[:15]
    stack.frameworks = sorted(list(frameworks))
    stack.test_frameworks = sorted(list(test_frameworks))
    stack.package_managers = sorted(list(pms))
    return stack


# ─── Testing Surface & Gap Analysis ──────────────────────────────────────────

def analyze_tests(source_files: List[str]) -> TestSurface:
    test_files = []
    pure_sources = []

    test_pattern = re.compile(r"(test_.*\.py|.*_test\.py|.*\.test\.[jt]sx?|.*\.spec\.[jt]sx?|^tests/|/__tests__/)", re.IGNORECASE)

    for sf in source_files:
        if test_pattern.search(sf):
            test_files.append(sf)
        else:
            pure_sources.append(sf)

    # Heuristic matching: find source modules that have no corresponding test file
    test_stems = {Path(t).stem.lower().replace("test_", "").replace("_test", "").replace(".test", "").replace(".spec", "") for t in test_files}
    
    untested = []
    for s in pure_sources:
        stem = Path(s).stem.lower()
        # Only check significant source code files
        if stem not in ["__init__", "index", "setup", "database", "database_test"] and stem not in test_stems:
            untested.append(s)

    return TestSurface(
        test_files=test_files,
        source_files=pure_sources,
        untested_sources=untested[:10],
        has_tests=len(test_files) > 0
    )


# ─── Intent & README Extractor ───────────────────────────────────────────────

def extract_readme_intent(root: Path) -> str:
    readme_path = root / "README.md"
    if not readme_path.exists():
        readme_path = root / "readme.md"
    if not readme_path.exists():
        return ""

    try:
        content = readme_path.read_text(encoding="utf-8", errors="ignore").strip()
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        
        # Grab the top header & first 2 descriptive paragraphs
        summary_lines = []
        for line in lines[:8]:
            if line.startswith("#"):
                summary_lines.append(line.lstrip("#").strip())
            elif not line.startswith("!") and not line.startswith("[") and len(line) > 10:
                summary_lines.append(line)
            if len(summary_lines) >= 3:
                break
        return " | ".join(summary_lines)
    except Exception:
        return ""


# ─── Core Scanner ────────────────────────────────────────────────────────────

def scan_project(root_dir: str = ".") -> ProjectSummary:
    root = Path(root_dir).resolve()
    
    file_extensions: Dict[str, int] = {}
    source_files: List[str] = []
    tree_lines: List[str] = []
    total_files = 0
    total_lines = 0

    # Walk directory while respecting ignores
    for dirpath, dirnames, filenames in os.walk(root):
        # Filter dirnames in-place to avoid descending into ignored dirs
        dirnames[:] = [
            d for d in dirnames 
            if d not in DEFAULT_IGNORES and not d.startswith(".")
        ]

        rel_dir = os.path.relpath(dirpath, root)
        depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
        
        if depth <= 2:
            prefix = "  " * depth
            dir_label = os.path.basename(dirpath) if rel_dir != "." else root.name
            tree_lines.append(f"{prefix}📁 {dir_label}/")

        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if f in DEFAULT_IGNORES or ext in IGNORED_EXTENSIONS or f.startswith("."):
                continue

            full_p = Path(dirpath) / f
            rel_p = os.path.relpath(full_p, root).replace("\\", "/")

            total_files += 1
            file_extensions[ext] = file_extensions.get(ext, 0) + 1
            source_files.append(rel_p)

            if depth <= 2 and len(tree_lines) < 35:
                prefix = "  " * (depth + 1)
                tree_lines.append(f"{prefix}📄 {f}")

            # Sample line count for text/source files
            if ext in [".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".md", ".json"]:
                try:
                    with open(full_p, "rb") as fp:
                        total_lines += sum(1 for _ in fp)
                except Exception:
                    pass

    # Build sub-components
    stack = detect_stack(root, file_extensions)
    git = get_git_activity(root)
    tests = analyze_tests(source_files)
    intent = extract_readme_intent(root)

    return ProjectSummary(
        root_path=str(root),
        project_name=root.name,
        readme_intent=intent,
        total_files=total_files,
        total_lines=total_lines,
        stack=stack,
        git=git,
        tests=tests,
        file_tree_snippet="\n".join(tree_lines[:25])
    )


# ─── Token-Efficient Prompt Injector (for LLMs) ──────────────────────────────

def build_llm_project_context(summary: ProjectSummary, focus_file: Optional[str] = None) -> str:
    """
    Generates a dense, token-budgeted string (~150-250 tokens) describing the project.
    Ready to insert directly into agent.py system/user prompts.
    """
    lines = []
    # 1. Project identity & primary stack
    stack_str = f"{summary.stack.primary_language}"
    if summary.stack.frameworks:
        stack_str += f" ({', '.join(summary.stack.frameworks)})"
    lines.append(f"Project: {summary.project_name} | Stack: {stack_str} | Files: {summary.total_files}")

    # 2. Project purpose (if available)
    if summary.readme_intent:
        lines.append(f"Intent: {summary.readme_intent[:140]}")

    # 3. Git activity & Hotspots
    if summary.git.is_git_repo:
        recent_msg = summary.git.recent_commits[0]["message"] if summary.git.recent_commits else "none"
        hotspots = ", ".join([h["file"] for h in summary.git.hotspot_files[:3]])
        git_line = f"Git: branch={summary.git.branch}, last_commit='{recent_msg[:50]}'"
        if hotspots:
            git_line += f", hotspots=[{hotspots}]"
        lines.append(git_line)

    # 4. Testing surface & gaps
    if summary.tests.has_tests:
        test_count = len(summary.tests.test_files)
        lines.append(f"Tests: {test_count} test files detected ({', '.join(summary.stack.test_frameworks) or 'standard'})")
    else:
        lines.append("Tests: No test files detected across codebase.")

    if focus_file:
        lines.append(f"Active File: {focus_file}")

    return "\n".join(lines)


# ─── Terminal Pretty Printer for CLI ─────────────────────────────────────────

def format_cli_summary(summary: ProjectSummary) -> str:
    """Returns a rich formatted report for terminal output."""
    sep = "=" * 60
    out = [
        sep,
        f"  ZEN AGENT - LAYER 1: PROJECT AWARENESS SCAN",
        f" Project: {summary.project_name} ({summary.root_path})",
        sep,
        f" * Primary Stack  : {summary.stack.primary_language}",
        f" * Frameworks    : {', '.join(summary.stack.frameworks) or 'None detected'}",
        f" * Test Tools     : {', '.join(summary.stack.test_frameworks) or 'None detected'}",
        f" * Codebase Size  : {summary.total_files} tracked files (~{summary.total_lines:,} lines)",
    ]

    if summary.readme_intent:
        out.append(f" * Stated Purpose : {summary.readme_intent[:100]}...")

    out.append(sep)
    out.append(" [Git Activity & Velocity]")
    if summary.git.is_git_repo:
        out.append(f"    Branch        : {summary.git.branch}")
        out.append(f"    Past 7 Days   : {summary.git.commits_last_7_days} commits")
        if summary.git.recent_commits:
            out.append("    Recent Log    :")
            for c in summary.git.recent_commits[:4]:
                out.append(f"      - [{c['hash']}] {c['message']} ({c['time']})")
        if summary.git.hotspot_files:
            out.append("    Hotspots      :")
            for h in summary.git.hotspot_files[:3]:
                out.append(f"      - {h['file']} ({h['changes']} recent modifications)")
        if summary.git.uncommitted_files:
            out.append(f"    Uncommitted   : {len(summary.git.uncommitted_files)} modified files")
    else:
        out.append("    (Not a Git repository)")

    out.append(sep)
    out.append(" [Test Surface & Blind Spots]")
    if summary.tests.has_tests:
        out.append(f"    Test Files    : {len(summary.tests.test_files)} files")
        for tf in summary.tests.test_files[:3]:
            out.append(f"      - {tf}")
    else:
        out.append("    [!] No automated test files found in project.")

    if summary.tests.untested_sources:
        out.append("    Potential Test Gaps (Untested Sources):")
        for uf in summary.tests.untested_sources[:4]:
            out.append(f"      ? {uf}")

    out.append(sep)
    return "\n".join(out)


# ─── Self-Test CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    # Ensure UTF-8 stdout if supported
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    print(f"Scanning target: {target} ...\n")
    proj = scan_project(target)
    print(format_cli_summary(proj))
    print("\n--- Token-Efficient LLM Context Preview ---")
    print(build_llm_project_context(proj))
