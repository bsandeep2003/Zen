"""
codebase/indexer.py — Symbol and import extraction from source files.

Uses regex-based parsing (no AST dependency) to extract:
  - Function definitions
  - Class definitions
  - Method definitions
  - Import statements

Supports Python and JavaScript/TypeScript.
"""
import re
from pathlib import Path
from typing import List

from codebase.model import CodebaseModel, SymbolInfo, ImportInfo


# ─── Python patterns ────────────────────────────────────────────────────────

PY_FUNC = re.compile(r"^(\s*)def\s+(\w+)\s*\(([^)]*)\)\s*(->.*?)?:", re.MULTILINE)
PY_CLASS = re.compile(r"^class\s+(\w+)\s*(\([^)]*\))?:", re.MULTILINE)
PY_IMPORT = re.compile(r"^(?:from\s+([\w.]+)\s+)?import\s+(.+)", re.MULTILINE)

# ─── JavaScript/TypeScript patterns ──────────────────────────────────────────

JS_FUNC = re.compile(
    r"(?:^|\s)(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
    re.MULTILINE,
)
JS_ARROW = re.compile(
    r"(?:^|\s)(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>",
    re.MULTILINE,
)
JS_CLASS = re.compile(r"(?:^|\s)(?:export\s+)?class\s+(\w+)", re.MULTILINE)
JS_IMPORT = re.compile(
    r"import\s+(?:\{([^}]+)\}|(\w+))\s+from\s+['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)


def _index_python(content: str, rel_path: str) -> tuple[List[SymbolInfo], List[ImportInfo]]:
    """Extract symbols and imports from Python source."""
    symbols: List[SymbolInfo] = []
    imports: List[ImportInfo] = []
    lines = content.splitlines()

    for match in PY_FUNC.finditer(content):
        indent = match.group(1)
        name = match.group(2)
        params = match.group(3).strip()
        ret = (match.group(4) or "").strip()
        line_no = content[:match.start()].count("\n") + 1
        kind = "method" if len(indent) > 0 else "function"
        sig = f"def {name}({params}){' ' + ret if ret else ''}:"
        symbols.append(SymbolInfo(
            name=name, kind=kind, file_path=rel_path,
            line_number=line_no, signature=sig,
        ))

    for match in PY_CLASS.finditer(content):
        name = match.group(1)
        bases = (match.group(2) or "").strip("()")
        line_no = content[:match.start()].count("\n") + 1
        sig = f"class {name}({bases}):" if bases else f"class {name}:"
        symbols.append(SymbolInfo(
            name=name, kind="class", file_path=rel_path,
            line_number=line_no, signature=sig,
        ))

    for match in PY_IMPORT.finditer(content):
        from_mod = match.group(1) or ""
        imported = match.group(2).strip()
        line_no = content[:match.start()].count("\n") + 1
        names = [n.strip().split(" as ")[0].strip() for n in imported.split(",")]
        module = from_mod if from_mod else names[0]
        imports.append(ImportInfo(
            module=module, names=names, file_path=rel_path,
            line_number=line_no, is_relative=from_mod.startswith("."),
        ))

    return symbols, imports


def _index_javascript(content: str, rel_path: str) -> tuple[List[SymbolInfo], List[ImportInfo]]:
    """Extract symbols and imports from JavaScript/TypeScript source."""
    symbols: List[SymbolInfo] = []
    imports: List[ImportInfo] = []

    for match in JS_FUNC.finditer(content):
        name = match.group(1)
        params = match.group(2).strip()
        line_no = content[:match.start()].count("\n") + 1
        symbols.append(SymbolInfo(
            name=name, kind="function", file_path=rel_path,
            line_number=line_no, signature=f"function {name}({params})",
        ))

    for match in JS_ARROW.finditer(content):
        name = match.group(1)
        line_no = content[:match.start()].count("\n") + 1
        symbols.append(SymbolInfo(
            name=name, kind="function", file_path=rel_path,
            line_number=line_no, signature=f"const {name} = (...) =>",
        ))

    for match in JS_CLASS.finditer(content):
        name = match.group(1)
        line_no = content[:match.start()].count("\n") + 1
        symbols.append(SymbolInfo(
            name=name, kind="class", file_path=rel_path,
            line_number=line_no, signature=f"class {name}",
        ))

    for match in JS_IMPORT.finditer(content):
        named = match.group(1)
        default = match.group(2)
        module = match.group(3)
        line_no = content[:match.start()].count("\n") + 1
        names = []
        if named:
            names = [n.strip().split(" as ")[0].strip() for n in named.split(",")]
        elif default:
            names = [default]
        imports.append(ImportInfo(
            module=module, names=names, file_path=rel_path,
            line_number=line_no, is_relative=module.startswith("."),
        ))

    return symbols, imports


def index_file(content: str, rel_path: str, language: str) -> tuple[List[SymbolInfo], List[ImportInfo]]:
    """Index a single file for symbols and imports."""
    if language == "Python":
        return _index_python(content, rel_path)
    elif language in ("JavaScript", "TypeScript"):
        return _index_javascript(content, rel_path)
    return [], []


def index_project(model: CodebaseModel) -> CodebaseModel:
    """
    Run symbol/import extraction across all source files in the model.

    Reads each source file and populates model.symbols and model.imports.
    Designed to be called once after scanning, then incrementally via
    index_file() for individual file updates.
    """
    model.symbols.clear()
    model.imports.clear()

    for rel_path, file_info in model.files.items():
        if file_info.language not in ("Python", "JavaScript", "TypeScript"):
            continue
        if file_info.size_bytes > 500_000:  # Skip very large files
            continue

        try:
            content = Path(file_info.path).read_text(encoding="utf-8", errors="ignore")
            syms, imps = index_file(content, rel_path, file_info.language)
            model.symbols.extend(syms)
            model.imports.extend(imps)
        except Exception:
            continue

    return model


def reindex_file(model: CodebaseModel, rel_path: str) -> CodebaseModel:
    """
    Re-index a single file (after it was modified).
    Removes old symbols/imports for this file and re-extracts them.
    """
    # Remove old entries
    model.symbols = [s for s in model.symbols if s.file_path != rel_path]
    model.imports = [i for i in model.imports if i.file_path != rel_path]

    file_info = model.files.get(rel_path)
    if not file_info or file_info.language not in ("Python", "JavaScript", "TypeScript"):
        return model

    try:
        content = Path(file_info.path).read_text(encoding="utf-8", errors="ignore")
        syms, imps = index_file(content, rel_path, file_info.language)
        model.symbols.extend(syms)
        model.imports.extend(imps)
    except Exception:
        pass

    return model
