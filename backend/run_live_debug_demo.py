"""
run_live_debug_demo.py — Script to trigger Zen Agent on a broken test file and print the results.
"""
import asyncio
import os
from pathlib import Path

from agent.session import ActiveSession
from agent.core import DebugAgentEngine
from codebase.scanner import scan_project
from tools.filesystem import read_file


async def demo_bug_fix():
    root_path = str(Path(__file__).resolve().parent.parent)
    test_cmd = "python test_sample_calculator.py"

    print("==================================================")
    print("1. BREAKING THE CODE: Created sample_calculator.py with a bug (returns a - b instead of a + b)")
    print("2. RUNNING FAILING TEST:")
    print(f"   Command: {test_cmd}")
    print("==================================================")

    session = ActiveSession(
        session_id="demo-fix-session",
        project_path=root_path,
        initial_command=test_cmd,
        max_attempts=3,
    )

    engine = DebugAgentEngine(session)
    print("\n[AGENT] LAUNCHING ZEN AUTONOMOUS AGENT LOOP...")
    status = await engine.run_debugging_loop()

    print("\n==================================================")
    print(f"3. AGENT FINISHED WITH STATUS: {(status or session.status or 'completed').upper()}")
    print("==================================================")

    # Check fixed file content
    fixed_code = read_file(root_path, "backend/sample_calculator.py")
    print("\n[FIXED CODE] Content of backend/sample_calculator.py:")
    print(fixed_code)


if __name__ == "__main__":
    asyncio.run(demo_bug_fix())
