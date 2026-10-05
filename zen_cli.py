"""
zen_cli.py — The `zen` CLI entry point.

Usage:
    zen fix "python main.py"       → Debug a failing command
    zen fix "npm run build"        → Debug any build/test command
    zen proceed                    → Re-run last failed command from .zen/ memory
    zen status                     → Show .zen/ memory summary for current project
    zen forget                     → Clear .zen/ memory for current project

The CLI automatically:
  1. Detects the project directory (cwd)
  2. Starts the FastAPI backend on an available port
  3. Starts the React frontend
  4. Opens your browser to the Zen dashboard
  5. Sends the debug command to the agent API
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import httpx

# Reconfigure stdout/stderr for Unicode support on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ─── Paths ────────────────────────────────────────────────────────────────────

ZEN_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ZEN_ROOT / "backend"
FRONTEND_DIR = ZEN_ROOT / "frontend"
ZEN_LOCAL_DIR = ".zen"
LAST_COMMAND_FILE = "last_command.json"


def find_available_port(start: int = 8000, end: int = 8100) -> int:
    """Find an available TCP port."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def wait_for_server(url: str, timeout: int = 30) -> bool:
    """Wait for a server to become available."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(url, timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def is_zen_backend(port: int) -> bool:
    """Check that whatever listens on `port` is actually the Zen API.

    Port 8000 being busy is not proof a compatible Zen backend is there — it
    could be any other service. Probing the identity endpoint avoids sending
    debug requests to an unrelated server.
    """
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/", timeout=3)
        if r.status_code != 200:
            return False
        data = r.json()
        return isinstance(data, dict) and data.get("app", "").startswith("Zen")
    except Exception:
        return False


def wait_for_zen_backend(port: int, timeout: int = 40) -> bool:
    """Wait for a genuine Zen backend to answer on `port`."""
    start = time.time()
    while time.time() - start < timeout:
        if is_zen_backend(port):
            return True
        time.sleep(0.5)
    return False


def wait_for_http(url: str, timeout: int = 60) -> bool:
    """Wait for any 2xx/3xx response from a URL."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            if httpx.get(url, timeout=3).status_code < 400:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def save_last_command(project_path: str, command: str):
    """Save the last debug command in .zen/ for `zen proceed`."""
    zen_dir = Path(project_path) / ZEN_LOCAL_DIR
    zen_dir.mkdir(exist_ok=True)
    (zen_dir / LAST_COMMAND_FILE).write_text(
        json.dumps({"command": command, "project_path": project_path}),
        encoding="utf-8"
    )


def load_last_command(project_path: str) -> str:
    """Load the last debug command from .zen/."""
    last_cmd_path = Path(project_path) / ZEN_LOCAL_DIR / LAST_COMMAND_FILE
    if last_cmd_path.exists():
        try:
            data = json.loads(last_cmd_path.read_text(encoding="utf-8"))
            return data.get("command", "")
        except Exception:
            pass
    return ""


def load_last_command_project(project_path: str) -> str:
    """Load the project directory the last command was recorded against."""
    last_cmd_path = Path(project_path) / ZEN_LOCAL_DIR / LAST_COMMAND_FILE
    if last_cmd_path.exists():
        try:
            data = json.loads(last_cmd_path.read_text(encoding="utf-8"))
            return data.get("project_path", "")
        except Exception:
            pass
    return ""


def print_banner():
    """Print the Zen CLI banner."""
    print()
    print("  \033[36m╔══════════════════════════════════════════╗\033[0m")
    print("  \033[36m║\033[0m  \033[1;37m🧘 Zen — Autonomous Debugging Agent\033[0m     \033[36m║\033[0m")
    print("  \033[36m║\033[0m  \033[90mObserve → Diagnose → Patch → Verify\033[0m     \033[36m║\033[0m")
    print("  \033[36m╚══════════════════════════════════════════╝\033[0m")
    print()


def print_step(icon: str, msg: str):
    """Print a formatted step message."""
    print(f"  {icon}  {msg}")


def cmd_fix(args):
    """Handle `zen fix <command>`."""
    project_path = getattr(args, "project", None) or os.getcwd()
    command = args.command.strip()

    # Smart command parsing:
    # 1. If command is a direct file path (e.g. C:\Users\bsand\fun_pro\calculator.py or calculator.py)
    cmd_parts = command.split(maxsplit=1)
    target_candidate = cmd_parts[1] if len(cmd_parts) > 1 and cmd_parts[0].lower() in ("python", "python.exe", "py", "node") else command
    target_candidate = target_candidate.strip("\"'")

    cand_path = Path(target_candidate)
    if not cand_path.is_absolute():
        cand_path = (Path(project_path) / target_candidate).resolve()

    if cand_path.exists() and cand_path.is_file():
        project_path = str(cand_path.parent.resolve())
        if cand_path.suffix == ".py":
            command = f"python {cand_path.name}"
        elif cand_path.suffix in (".js", ".mjs"):
            command = f"node {cand_path.name}"
        else:
            command = cand_path.name
    elif command.endswith(".py") and not command.startswith("python"):
        command = f"python {command}"

    print_banner()
    print_step("📂", f"Project: \033[1m{project_path}\033[0m")
    print_step("🔧", f"Command: \033[1m{command}\033[0m")
    print()

    # Save last command for `zen proceed`
    save_last_command(project_path, command)

    # Check if backend is already running
    backend_port = 8000
    frontend_port = 3000

    if is_zen_backend(backend_port):
        print_step("✅", f"Backend active on port {backend_port}")
    else:
        if is_port_in_use(backend_port):
            # Someone else owns 8000 — don't hijack it, pick a free port.
            print_step("⚠️ ", f"Port {backend_port} is in use by another service; using a free port")
            backend_port = find_available_port(8001)
        print_step("🚀", "Starting Zen backend server...")
        env = os.environ.copy()
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--port", str(backend_port), "--host", "127.0.0.1"],
            cwd=str(BACKEND_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if wait_for_zen_backend(backend_port):
            print_step("✅", f"Backend ready on port {backend_port}")
        else:
            print_step("❌", f"No Zen backend responded on port {backend_port}.")
            print_step("💡", "Check backend/.env for API key configuration, then retry.")
            sys.exit(1)

    if is_port_in_use(frontend_port):
        print_step("✅", f"Frontend active on port {frontend_port}")
    else:
        print_step("🚀", "Starting Zen frontend...")
        # `serve` is not a local dependency, so npx may need to fetch it. Send
        # output to a log rather than DEVNULL so failures are diagnosable.
        frontend_log = open(BACKEND_DIR / "frontend_serve.log", "wb")
        subprocess.Popen(
            ["npx", "serve", "-s", "build", "-l", str(frontend_port)],
            cwd=str(FRONTEND_DIR),
            stdout=frontend_log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            shell=True,
        )
        if wait_for_http(f"http://127.0.0.1:{frontend_port}/", timeout=60):
            print_step("✅", f"Frontend ready on port {frontend_port}")
        else:
            print_step("⚠️ ", "Frontend did not come up in time — continuing without the dashboard.")
            print_step("💡", "Run `npm run build` in frontend/, or use `npm start` on port 3000.")
    # Send debug command to backend API
    print()
    print_step("⚡", "Starting autonomous debugging session...")
    print()

    try:
        r = httpx.post(
            f"http://127.0.0.1:{backend_port}/agent/start",
            json={
                "project_path": project_path,
                "initial_command": command,
                "max_attempts": 5,
            },
            timeout=10,
        )
        if r.status_code != 200:
            print_step("❌", f"Backend rejected the session (HTTP {r.status_code}).")
            print_step("💡", f"{r.text[:300]}")
            sys.exit(1)

        try:
            data = r.json()
        except Exception:
            print_step("❌", "Backend returned a non-JSON response:")
            print_step("💡", f"{r.text[:300]}")
            sys.exit(1)

        session_id = data.get("session_id")
        if not session_id:
            print_step("❌", f"Backend did not return a session id: {str(data)[:200]}")
            sys.exit(1)
        print_step("🧠", f"Session ID: \033[1;32m{session_id}\033[0m")

        # Open browser with session ID and encoded parameters (including backend port for WebSocket)
        import urllib.parse
        q_proj = urllib.parse.quote_plus(project_path)
        q_cmd = urllib.parse.quote_plus(command)
        dashboard_url = f"http://localhost:{frontend_port}/workspace?session={session_id}&project={q_proj}&command={q_cmd}&ws_port={backend_port}"
        print()
        print_step("🌐", f"Live Dashboard: \033[4m{dashboard_url}\033[0m")
        try:
            webbrowser.open(dashboard_url)
        except Exception:
            pass

        print()
        print(f"  \033[90m──────────────────────────────────────────────────\033[0m")
        print(f"  \033[90m  Observing ➔ Diagnosing ➔ Patching ➔ Verifying...\033[0m")
        print(f"  \033[90m──────────────────────────────────────────────────\033[0m")
        print()

        # Poll session status with live terminal feedback
        last_state = ""
        started = time.time()
        consecutive_errors = 0
        # Generous ceiling: an agent run makes several LLM calls. Without a
        # bound, a missing/bad session id would poll forever in silence.
        max_wait = 30 * 60

        while True:
            if time.time() - started > max_wait:
                print_step("⚠️ ", f"Gave up after {max_wait // 60} minutes. Check the dashboard.")
                sys.exit(1)

            time.sleep(1.2)
            try:
                sr = httpx.get(f"http://127.0.0.1:{backend_port}/agent/session/{session_id}", timeout=5)
                if sr.status_code != 200:
                    consecutive_errors += 1
                    if consecutive_errors == 3:
                        print_step("❌", f"Session lookup failed (HTTP {sr.status_code}: {sr.text[:120]})")
                    if consecutive_errors >= 10:
                        sys.exit(1)
                    continue

                consecutive_errors = 0
                sdata = sr.json()
                status = sdata.get("status", "running")
                attempts = sdata.get("attempts", [])
                cur_state = sdata.get("state") or ""

                latest = attempts[-1] if attempts else {}
                if cur_state and cur_state != last_state:
                    last_state = cur_state
                    attempt_n = latest.get("attempt_number") or sdata.get("total_attempts") or 1
                    if cur_state == "observe":
                        print_step("👁️ ", f"[Attempt {attempt_n}] Observing command error...")
                    elif cur_state == "diagnose":
                        diag = latest.get("diagnosis", "Analyzing error context...")
                        print_step("🔍", f"Diagnosing: {diag[:80]}...")
                    elif cur_state == "plan":
                        print_step("📋", "Planning fix strategy...")
                    elif cur_state == "patch":
                        print_step("🛠️ ", "Applying LLM-generated patch...")
                    elif cur_state == "verify":
                        print_step("🧪", "Verifying fix by re-running command...")

                if status == "success":
                    print()
                    print(f"  \033[1;32m══════════════════════════════════════════════════\033[0m")
                    print(f"  \033[1;32m  🎉 SUCCESS! Bug fixed & verified in {len(attempts)} attempt(s).\033[0m")
                    if attempts and attempts[-1].get("stdout"):
                        print(f"  \033[1;32m  Output: {attempts[-1]['stdout'].strip()}\033[0m")
                    print(f"  \033[1;32m  Fix saved to .zen/fixes.json for future runs.\033[0m")
                    print(f"  \033[1;32m══════════════════════════════════════════════════\033[0m")
                    print()
                    return 0
                elif status in ("failed", "escalated"):
                    print()
                    print(f"  \033[1;31m══════════════════════════════════════════════════\033[0m")
                    print(f"  \033[1;31m  ⚠️  Agent stopped: Status '{status}'.\033[0m")
                    if status == "escalated":
                        print(f"  \033[1;31m  It could not verify a fix — reverted to the original code.\033[0m")
                    print(f"  \033[1;31m══════════════════════════════════════════════════\033[0m")
                    print()
                    return 1

            except httpx.RequestError as e:
                consecutive_errors += 1
                if consecutive_errors == 3:
                    print_step("⚠️ ", f"Lost contact with backend: {e}")
                if consecutive_errors >= 10:
                    print_step("❌", "Backend unreachable. Stopping.")
                    sys.exit(1)

    except KeyboardInterrupt:
        print()
        print_step("🛑", "Stopped by user.")
        print()
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as e:
        print_step("❌", f"Failed: {e}")
        sys.exit(1)

    return 0


def find_project_zen_dir(project_path: str, max_levels: int = 6) -> str:
    """Nearest ancestor (including cwd) that has a .zen/ memory directory."""
    current = Path(project_path).resolve()
    for _ in range(max_levels):
        if (current / ZEN_LOCAL_DIR).is_dir():
            return str(current)
        if current.parent == current:
            break
        current = current.parent
    return ""


def cmd_proceed(args):
    """Handle `zen proceed` — re-run the last failed command."""
    cwd = os.getcwd()

    # The recorded command lives inside the project's .zen/ directory, and that
    # file is what names the project — so it cannot be used to find the project.
    # Resolve from --project, else the nearest .zen/ at or above the cwd.
    project_path = ""
    explicit = getattr(args, "project", None)
    if explicit:
        if (Path(explicit) / ZEN_LOCAL_DIR).is_dir():
            project_path = str(Path(explicit).resolve())
        else:
            print_banner()
            print_step("❌", f"No {ZEN_LOCAL_DIR}/ memory found in {explicit}")
            sys.exit(1)
    else:
        project_path = find_project_zen_dir(cwd)

    if not project_path:
        print_banner()
        print_step("❌", "No previous command found. Use `zen fix \"<command>\"` first.")
        print_step("💡", "Or target a project: `zen proceed --project <dir>`")
        sys.exit(1)

    last_cmd = load_last_command(project_path)

    # Fall back to the directory recorded inside the file, in case the memory
    # was written against a different path than where it now lives.
    if not last_cmd:
        recorded = load_last_command_project(project_path)
        if recorded and Path(recorded).is_dir():
            candidate_cmd = load_last_command(recorded)
            if candidate_cmd:
                last_cmd = candidate_cmd
                project_path = recorded

    if not last_cmd:
        print_banner()
        print_step("❌", "No previous command found. Use `zen fix \"<command>\"` first.")
        sys.exit(1)

    print_banner()
    if Path(project_path).resolve() != Path(cwd).resolve():
        print_step("📂", f"Using saved project: \033[1m{project_path}\033[0m")
    print_step("🔄", f"Re-running last command: \033[1m{last_cmd}\033[0m")
    # Reuse fix logic, pinned to the project the command was recorded against.
    args.command = last_cmd
    args.project = project_path
    return cmd_fix(args)


def cmd_status(args):
    """Handle `zen status` — show memory summary."""
    project_path = os.getcwd()
    zen_dir = Path(project_path) / ZEN_LOCAL_DIR

    print_banner()
    print_step("📂", f"Project: \033[1m{project_path}\033[0m")
    print()

    if not zen_dir.exists():
        print_step("📭", "No .zen/ memory found for this project.")
        print_step("💡", "Run `zen fix \"<command>\"` to start debugging and build memory.")
        return

    # Load memory
    memory_file = zen_dir / "memory.json"
    fixes_file = zen_dir / "fixes.json"

    if memory_file.exists():
        memory = json.loads(memory_file.read_text(encoding="utf-8"))
        tech = memory.get("tech_stack", {})
        if tech:
            print_step("🔧", f"Tech Stack: {tech.get('primary_language', '?')} ({', '.join(tech.get('frameworks', []))})")
        notes = memory.get("context_notes", [])
        if notes:
            print_step("📝", f"Context Notes: {len(notes)} saved")
            for n in notes[-3:]:
                print(f"       → {n.get('note', '')[:80]}")

    if fixes_file.exists():
        fixes = json.loads(fixes_file.read_text(encoding="utf-8"))
        successful = [f for f in fixes if f.get("was_successful")]
        print_step("🛠️ ", f"Fix History: {len(fixes)} total, {len(successful)} successful")
        if successful:
            print()
            print("  \033[90mRecent successful fixes:\033[0m")
            for fix in successful[-5:]:
                print(f"    ✅ {fix.get('error_type', '?')}: {fix.get('error_message', '?')[:60]}")
                print(f"       → Fix: {fix.get('diagnosis', '?')[:60]}")

    last_cmd = load_last_command(project_path)
    if last_cmd:
        print()
        print_step("🔄", f"Last command: \033[1m{last_cmd}\033[0m")
        print_step("💡", "Run `zen proceed` to re-run it.")

    print()


def cmd_forget(args):
    """Handle `zen forget` — clear .zen/ memory."""
    import shutil
    project_path = os.getcwd()
    zen_dir = Path(project_path) / ZEN_LOCAL_DIR

    print_banner()
    if zen_dir.exists():
        shutil.rmtree(zen_dir)
        print_step("🗑️ ", f"Cleared .zen/ memory for {project_path}")
    else:
        print_step("📭", "No .zen/ memory found.")
    print()


def main():
    parser = argparse.ArgumentParser(
        prog="zen",
        description="🧘 Zen — Autonomous Debugging Agent CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # zen fix "<command>"
    fix_parser = subparsers.add_parser("fix", help="Debug a failing command")
    fix_parser.add_argument("command", type=str, help="The failing command to debug (e.g., 'python main.py')")
    fix_parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Project directory to debug (defaults to the current directory)",
    )

    # zen proceed
    proceed_parser = subparsers.add_parser("proceed", help="Re-run the last failed command from .zen/ memory")
    proceed_parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Project directory holding the .zen/ memory (defaults to the nearest one above cwd)",
    )

    # zen status
    subparsers.add_parser("status", help="Show .zen/ memory summary for current project")

    # zen forget
    subparsers.add_parser("forget", help="Clear .zen/ memory for current project")

    args = parser.parse_args()

    # Propagate the command's exit status so scripts/CI can detect failures.
    if args.subcommand == "fix":
        sys.exit(cmd_fix(args) or 0)
    elif args.subcommand == "proceed":
        sys.exit(cmd_proceed(args) or 0)
    elif args.subcommand == "status":
        cmd_status(args)
    elif args.subcommand == "forget":
        cmd_forget(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
