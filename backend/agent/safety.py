"""
agent/safety.py — Safety controls for the debugging agent.

Enforces:
  - Max attempt limit (prevents infinite loops)
  - Error cycle detection (detects repeating errors or oscillating state)
  - Automatic rollback when patches fail
"""
import hashlib
from typing import List, Dict, Any, Tuple


class SafetyChecker:
    def __init__(self, max_attempts: int = 5):
        self.max_attempts = max_attempts
        self.error_signatures: List[str] = []

    def compute_error_signature(self, error_type: str, error_message: str, stderr: str) -> str:
        """Hash the error type + normalized message to identify identical errors."""
        raw = f"{error_type}:{error_message}:{stderr[:300]}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def check_attempt_limit(self, current_attempt: int) -> Tuple[bool, str]:
        """Check if max attempts exceeded."""
        if current_attempt > self.max_attempts:
            return True, f"Maximum debugging attempts ({self.max_attempts}) reached without resolution."
        return False, ""

    def check_cycle(self, error_type: str, error_message: str, stderr: str) -> Tuple[bool, str]:
        """Check if identical error was seen 2+ times in the same session."""
        sig = self.compute_error_signature(error_type, error_message, stderr)
        if self.error_signatures.count(sig) >= 2:
            return True, f"Repeated error cycle detected for '{error_type}: {error_message}'. Escalating to user."
        self.error_signatures.append(sig)
        return False, ""

    def should_rollback(self, previous_exit_code: int, current_exit_code: int) -> bool:
        """Determine if change made things worse (e.g. exit code changed from non-zero to a fatal crash)."""
        if current_exit_code != 0 and current_exit_code != previous_exit_code:
            return True
        return False
