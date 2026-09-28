"""
test_backend_agent.py — Test backend scanner, indexer, search, terminal executor, and DB schema.
"""
import asyncio
import os
from pathlib import Path
from codebase.scanner import scan_project
from codebase.model import CodebaseModel
from codebase.indexer import index_file
from codebase.search import correlation_search, search_code
from terminal.executor import execute_command
from database import init_db, SessionLocal
import crud


async def run_backend_tests():
    root_path = str(Path(__file__).resolve().parent.parent)
    print(f"Testing project scanning on {root_path}...")

    # 1. Test Codebase Scanner
    model = CodebaseModel(project_root=root_path)
    scan_project(root_path, model)
    print(f"[PASS] Codebase Scanner: {len(model.files)} files, primary language: {model.primary_language}")
    assert len(model.files) > 0

    # 2. Test Terminal Executor
    print("Testing Terminal Executor...")
    cmd_res = await execute_command("python --version", cwd=root_path)
    print(f"[PASS] Terminal Executor: exit_code={cmd_res.exit_code}, stdout={cmd_res.stdout.strip()}")
    assert cmd_res.exit_code == 0

    # 3. Test Symbol Indexer
    print("Testing Symbol Indexer on backend/main.py...")
    main_py = os.path.join(root_path, "backend", "main.py")
    main_py_path = Path(main_py)
    content = main_py_path.read_text(encoding="utf-8")
    symbols, imports = index_file(content, "backend/main.py", "Python")
    print(f"[PASS] Symbol Indexer: found {len(symbols)} symbols in main.py")
    assert len(symbols) > 0

    # 4. Test Code Search & Correlation
    print("Testing Code Search & Error Correlation...")
    sample_error = "File \"backend/main.py\", line 45, in start_agent_session\nKeyError: 'session_id'"
    correlated = correlation_search(root_path, sample_error, model)
    print(f"[PASS] Error Correlation: found {len(correlated)} correlated files: {[c['path'] for c in correlated]}")
    assert len(correlated) > 0

    # 5. Test DB Schema & CRUD
    print("Testing DB Init & CRUD...")
    await init_db()
    import uuid
    test_sid = f"test-session-{str(uuid.uuid4())[:8]}"
    async with SessionLocal() as db:
        sess = await crud.create_debug_session(
            db,
            session_id=test_sid,
            project_path=root_path,
            initial_command="pytest",
            max_attempts=3,
        )
        print(f"[PASS] Created debug session: {sess.session_id}")

        attempt = await crud.create_debug_attempt(
            db,
            session_id=test_sid,
            attempt_number=1,
            state="observe",
            diagnosis="Sample diagnosis",
            command_run="pytest",
            exit_code=1,
        )
        print(f"[PASS] Created debug attempt: #{attempt.attempt_number}")

        fetched = await crud.get_debug_session(db, test_sid)
        assert fetched is not None
        assert fetched.session_id == test_sid

    print("\nALL BACKEND CORE TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_backend_tests())
