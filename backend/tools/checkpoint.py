"""
tools/checkpoint.py — Real file snapshots so a failed patch can be undone.

`tools/git.py` advertises checkpoints/rollback but does not implement them:
`create_checkpoint` only reads `rev-parse HEAD`, and `rollback_checkpoint`
(which would run `git checkout -- .` + `git clean -fd`) is never called and
would be destructive anyway — it discards unrelated uncommitted work and
deletes untracked files.

This module snapshots the specific files the agent is about to modify and can
restore them exactly. It also works for projects that are not git repositories.
"""
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Set


@dataclass
class FileCheckpoint:
    """Original contents of the files modified during one attempt."""

    project_path: str
    session_id: str
    _originals: dict = field(default_factory=dict)  # relative path -> str | None
    _snapshotted: Set[str] = field(default_factory=set)

    def capture(self, rel_paths: Iterable[str]) -> None:
        """Record the current contents of each path (once)."""
        for rel in rel_paths:
            if not rel or rel in self._snapshotted:
                continue
            self._snapshotted.add(rel)
            try:
                abs_path = Path(self.project_path) / rel
                self._originals[rel] = (
                    abs_path.read_text(encoding="utf-8") if abs_path.is_file() else None
                )
            except Exception:
                # Unreadable/binary file: record as absent so we never touch it.
                self._originals[rel] = None

    @property
    def touched(self) -> List[str]:
        return sorted(self._snapshotted)

    def restore(self) -> List[str]:
        """Put every captured file back. Returns the paths actually restored.

        Files created by the agent (originally absent) are removed.
        """
        restored = []
        for rel, original in self._originals.items():
            try:
                abs_path = Path(self.project_path) / rel
                if original is None:
                    if abs_path.is_file():
                        abs_path.unlink()
                        restored.append(rel)
                else:
                    current = abs_path.read_text(encoding="utf-8") if abs_path.is_file() else None
                    if current != original:
                        abs_path.write_text(original, encoding="utf-8")
                        restored.append(rel)
            except Exception:
                continue
        return restored


def cleanup_checkpoint_dir(project_path: str) -> None:
    """Remove any stale temp checkpoint dir (kept for API symmetry)."""
    stale = Path(project_path) / ".zen" / ".checkpoints"
    if stale.is_dir():
        shutil.rmtree(stale, ignore_errors=True)
