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

    if is_port_in_use(backend_port):
        print_step("✅", f"Backend active on port {backend_port}")
    else:
        print_step("🚀", "Starting Zen backend server...")
        backend_port = find_available_port(8000)
        env = os.environ.copy()
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--port", str(backend_port), "--host", "127.0.0.1"],
            cwd=str(BACKEND_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if wait_for_server(f"http://127.0.0.1:{backend_port}/health"):
            print_step("✅", f"Backend ready on port {backend_port}")
        else:
            print_step("❌", "Backend failed to start. Check backend/.env for API key configuration.")
            sys.exit(1)

    if is_port_in_use(frontend_port):
        print_step("✅", f"Frontend active on port {frontend_port}")
    else:
        print_step("🚀", "Starting Zen frontend...")
        subprocess.Popen(
            ["npx", "serve", "-s", "build", "-l", str(frontend_port)],
            cwd=str(FRONTEND_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            shell=True,
        )
        time.sleep(2)
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
        data = r.json()
        session_id = data.get("session_id", "unknown")
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
        while True:
            time.sleep(1.2)
            try:
                sr = httpx.get(f"http://127.0.0.1:{backend_port}/agent/session/{session_id}", timeout=5)
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
                    print(f"  \033[1;32m  Fix saved to .zen/memory.json for future runs.\033[0m")
                    print(f"  \033[1;32m══════════════════════════════════════════════════\033[0m")
                    print()
                    return
                elif status in ("failed", "escalated"):
                    print()
                    print(f"  \033[1;31m══════════════════════════════════════════════════\033[0m")
                    print(f"  \033[1;31m  ⚠️ Agent stopped: Status '{status}'. Check dashboard.\033[0m")
                    print(f"  \033[1;31m══════════════════════════════════════════════════\033[0m")
                    print()
                    return

            except httpx.RequestError:
                pass

    except KeyboardInterrupt:
        print()
        print_step("🛑", "Stopped by user.")
        print()
    except Exception as e:
        print_step("❌", f"Failed: {e}")
        sys.exit(1)


def cmd_proceed(args):
    """Handle `zen proceed` — re-run the last failed command."""
    project_path = os.getcwd()
    last_cmd = load_last_command(project_path)

    if not last_cmd:
        print_banner()
        print_step("❌", "No previous command found. Use `zen fix \"<command>\"` first.")
        sys.exit(1)

    print_banner()
    print_step("🔄", f"Re-running last command: \033[1m{last_cmd}\033[0m")
    # Reuse fix logic
    args.command = last_cmd
    cmd_fix(args)


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

    # zen proceed
    subparsers.add_parser("proceed", help="Re-run the last failed command from .zen/ memory")

    # zen status
    subparsers.add_parser("status", help="Show .zen/ memory summary for current project")

    # zen forget
    subparsers.add_parser("forget", help="Clear .zen/ memory for current project")

    args = parser.parse_args()

    if args.subcommand == "fix":
        cmd_fix(args)
    elif args.subcommand == "proceed":
        cmd_proceed(args)
    elif args.subcommand == "status":
        cmd_status(args)
    elif args.subcommand == "forget":
        cmd_forget(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
