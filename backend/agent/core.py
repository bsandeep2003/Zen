"""
agent/core.py — Autonomous Debugging Agent Engine.

Executes the observe → diagnose → plan → patch → verify state machine.
Uses Groq LLM tool calling to inspect code, apply patches, run commands, and verify fixes.

Memory-aware: reads from and writes to the project's .zen/ directory
to remember past fixes and skip redundant analysis.
"""
import json
import logging
import time
from typing import Dict, Any, Optional, List

from codebase.scanner import scan_project, update_codebase_model
from codebase.search import correlation_search, search_code, find_symbol
from terminal.executor import execute_command
from tools.filesystem import list_files, read_file, write_file
from tools.patch import apply_patch
from tools.git import create_checkpoint, rollback_checkpoint, get_git_diff
from llm.client import get_groq_client, chat_completion
from llm.prompts import SYSTEM_PROMPT_AGENT, DEBUGGER_TOOLS
from llm.context import build_agent_context
from agent.session import ActiveSession
from memory.store import (
    init_memory, has_memory, load_memory, save_memory,
    load_fixes, save_fix, find_similar_fix,
    save_project_map, update_tech_stack, add_context_note,
    get_memory_summary,
)
import crud
from database import SessionLocal

logger = logging.getLogger(__name__)


def execute_agent_tool(project_path: str, codebase: Any, func_name: str, args: dict) -> Dict[str, Any]:
    """Execute a tool called by the LLM and return structured result."""
    try:
        if func_name == "read_file":
            path = args.get("path") or args.get("file_path", "")
            content = read_file(project_path, path)
            return {"success": True, "content": content}
            
        elif func_name == "list_files":
            path = args.get("path", ".")
            files = list_files(project_path, path)
            return {"success": True, "files": files}

        elif func_name == "search_code":
            query = args.get("query", "")
            matches = search_code(codebase, query)
            return {"success": True, "results": [m.to_dict() for m in matches]}

        elif func_name == "find_symbol":
            name = args.get("name", "")
            syms = find_symbol(codebase, name)
            return {"success": True, "symbols": syms}

        elif func_name == "apply_patch":
            rel_path = args.get("file_path") or args.get("path", "")
            search = args.get("search", "")
            replace = args.get("replace", "")
            return apply_patch(project_path, rel_path, search, replace)

        elif func_name == "create_file":
            rel_path = args.get("path") or args.get("file_path", "")
            content = args.get("content", "")
            msg = write_file(project_path, rel_path, content)
            return {"success": True, "message": msg, "file_path": rel_path}

        elif func_name == "run_command":
            cmd = args.get("command", "")
            res = execute_command(cmd, cwd=project_path)
            return res.to_dict()

        else:
            return {"success": False, "error": f"Unknown tool: {func_name}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def generate_plain_english_explanation(error_type: str, error_message: str, diagnosis: str, modified_files: list) -> dict:
    """Generate clear, non-technical plain English explanations of why code failed and how it was fixed."""
    err_str = f"{error_type}: {error_message}"
    if "No module named" in err_str or "ModuleNotFoundError" in err_str:
        if ".py" in err_str:
            why = "Python Import Syntax Error: The code wrote `from <module>.py import ...`. Python treats `.py` as a sub-package instead of a file name. In Python, you must omit `.py` from import statements."
            fix = f"Removed the `.py` extension from the import statement in `{', '.join(modified_files) if modified_files else 'the source file'}`."
        else:
            why = f"Module Not Found: Python could not locate the imported module: {error_message.strip()}."
            fix = f"Corrected the import statement and aligned file paths in `{', '.join(modified_files) if modified_files else 'the source file'}`."
    elif "SyntaxError" in err_str:
        why = f"Syntax Error: The code contains invalid language syntax: {error_message.strip()}."
        fix = f"Corrected the syntax structure in `{', '.join(modified_files) if modified_files else 'the source file'}`."
    elif "ZeroDivisionError" in err_str:
        why = "Division by Zero: Code attempted to divide a number by 0, which is invalid."
        fix = f"Added safety checks / default fallbacks in `{', '.join(modified_files) if modified_files else 'the source file'}`."
    elif "TypeError" in err_str:
        why = f"Type Error: Unexpected data types or incorrect argument count: {error_message.strip()}."
        fix = f"Aligned argument types and parameters in `{', '.join(modified_files) if modified_files else 'the source file'}`."
    elif "NameError" in err_str:
        why = f"Undefined Variable/Function: {error_message.strip()}."
        fix = f"Defined the missing variable or imported the required definition in `{', '.join(modified_files) if modified_files else 'the source file'}`."
    else:
        why = diagnosis if diagnosis else f"Execution failed with {error_type}: {error_message.strip()}"
        fix = f"Applied targeted patch in `{', '.join(modified_files) if modified_files else 'the codebase'}` to eliminate the error."

    return {
        "why_failed": why,
        "what_fixed": fix,
        "files_modified": modified_files,
        "error_type": error_type,
        "error_message": error_message,
    }


class DebugAgentEngine:
    def __init__(self, session: ActiveSession):
        self.session = session

    async def run_debugging_loop(self):
        """Main autonomous loop with .zen/ memory integration."""
        session = self.session
        await session.broadcast("agent_started", {"initial_command": session.initial_command})

        # ─── MEMORY: Initialize .zen/ and load project memory ─────────────
        init_memory(session.project_path)
        memory_summary = get_memory_summary(session.project_path)

        if memory_summary["has_memory"] and memory_summary["total_fixes"] > 0:
            await session.broadcast("memory_loaded", {
                "message": "Loading .zen/ memory...",
                "tech_stack": memory_summary.get("tech_stack", {}),
                "total_fixes": memory_summary["total_fixes"],
                "successful_fixes": memory_summary["successful_fixes"],
                "recent_fixes": memory_summary.get("recent_fixes", []),
                "context_notes": memory_summary.get("context_notes", []),
            })
        else:
            await session.broadcast("memory_loaded", {
                "message": "No prior memory found. Building fresh project context...",
                "tech_stack": {},
                "total_fixes": 0,
                "successful_fixes": 0,
                "recent_fixes": [],
                "context_notes": [],
            })

        # Step 0: Initial codebase scan
        scan_project(session.project_path, session.codebase)
        await session.broadcast("codebase_scanned", {"summary": session.codebase.get_summary()})

        # Save project map to .zen/ for faster future loads
        save_project_map(session.project_path, session.codebase.to_dict())
        update_tech_stack(
            session.project_path,
            session.codebase.primary_language,
            session.codebase.frameworks,
        )

        # Run initial command to capture error
        await session.broadcast("state_change", {"state": "observe", "msg": "Running initial command..."})
        cmd_result = await execute_command(session.initial_command, cwd=session.project_path)
        session.execution.add_result(cmd_result)

        if cmd_result.exit_code == 0:
            session.status = "success"
            session.state = "success"
            await session.broadcast("completed", {"message": "Initial command succeeded! No error detected."})
            return

        while session.status == "active":
            session.current_attempt_number += 1
            attempt_num = session.current_attempt_number

            # Check safety limits
            exceeded, limit_msg = session.safety.check_attempt_limit(attempt_num)
            if exceeded:
                session.status = "failed"
                session.state = "failure"
                await session.broadcast("failed", {"error": limit_msg})
                break

            last_result = session.execution.command_history[-1]
            exec_summary = session.execution.to_summary()
            error_type = exec_summary.get("last_error_type") or "RuntimeError"
            error_msg = exec_summary.get("last_error_message") or last_result.stderr[:200]

            # Check for repeating cycles
            is_cycle, cycle_msg = session.safety.check_cycle(error_type, error_msg, last_result.stderr)
            if is_cycle:
                session.status = "escalated"
                session.state = "failure"
                await session.broadcast("escalated", {"error": cycle_msg})
                break

            # ─── MEMORY: Check for similar past fixes ─────────────────────
            similar_fix = find_similar_fix(session.project_path, error_type, error_msg)
            if similar_fix:
                await session.broadcast("strategy", {
                    "type": "memory_match",
                    "message": f"Found a similar past fix for '{error_type}'",
                    "past_fix": {
                        "error_type": similar_fix.get("error_type", ""),
                        "error_message": similar_fix.get("error_message", "")[:100],
                        "diagnosis": similar_fix.get("diagnosis", "")[:200],
                        "files_modified": similar_fix.get("files_modified", []),
                        "timestamp": similar_fix.get("timestamp", ""),
                    },
                    "strategy": f"I've seen this error before. Previously fixed by: {similar_fix.get('diagnosis', 'unknown')[:150]}. Will try a similar approach.",
                })
            else:
                await session.broadcast("strategy", {
                    "type": "fresh_analysis",
                    "message": f"New error type '{error_type}' — performing full analysis",
                    "strategy": "No matching fix in memory. I will read the error trace, correlate to source files, diagnose the root cause, and apply a targeted patch.",
                })

            # ─── STATE 1: OBSERVE ─────────────────────────────────────────────
            session.state = "observe"
            await session.broadcast("state_change", {
                "state": "observe",
                "attempt": attempt_num,
                "error_type": error_type,
                "error_message": error_msg,
                "stderr": last_result.stderr,
            })

            # Correlate error to files
            correlated_files = correlation_search(session.project_path, last_result.stderr, session.codebase)

            # Build context payload
            context_data = build_agent_context(
                session.codebase, session.execution, session.attempts, "diagnose"
            )
            context_data["correlated_files"] = correlated_files

            # Inject memory context if available
            if similar_fix:
                context_data["memory_hint"] = {
                    "similar_past_fix": similar_fix.get("diagnosis", ""),
                    "files_previously_modified": similar_fix.get("files_modified", []),
                }

            # ─── STATE 2 & 3: DIAGNOSE, PLAN & TOOL LOOP ───────────────────────
            session.state = "diagnose"
            await session.broadcast("state_change", {
                "state": "diagnose",
                "attempt": attempt_num,
                "correlated_files": [f["path"] for f in correlated_files],
            })

            # Build prompt with optional memory context
            memory_hint_text = ""
            if similar_fix:
                memory_hint_text = f"\n\n**Memory Hint**: A similar error was fixed before. Previous diagnosis: '{similar_fix.get('diagnosis', '')}'. Files modified: {similar_fix.get('files_modified', [])}. Consider a similar approach, but verify the current state first."

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT_AGENT},
                {
                    "role": "user",
                    "content": f"Context:\n```json\n{json.dumps(context_data, indent=2)}\n```\nAnalyze the error, inspect relevant files using read_file or search_code if needed, and apply a targeted patch using apply_patch.{memory_hint_text}",
                },
            ]

            client = get_groq_client()
            chk = create_checkpoint(session.project_path, session.session_id)
            
            patch_applied = False
            modified_files = []
            patch_diff_text = ""
            diagnosis_text = ""

            # Multi-turn tool loop (up to 4 turns)
            for turn in range(4):
                response = await chat_completion(client, messages, tools=DEBUGGER_TOOLS)
                assistant_msg = response["message"]
                
                diagnosis_text = assistant_msg.get("content") or diagnosis_text or "Analyzing trace and codebase context..."
                tool_calls = assistant_msg.get("tool_calls", [])

                if not tool_calls:
                    break

                session.state = "patch"
                await session.broadcast("state_change", {
                    "state": "patch",
                    "attempt": attempt_num,
                    "diagnosis": diagnosis_text,
                    "tool_calls_count": len(tool_calls),
                })

                # Append assistant response to message history
                messages.append({
                    "role": "assistant",
                    "content": assistant_msg.get("content", ""),
                    "tool_calls": [
                        {
                            "id": tc.get("id", f"call_{i}"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name") or tc.get("function", {}).get("name"),
                                "arguments": json.dumps(tc.get("arguments", {})) if isinstance(tc.get("arguments"), dict) else tc.get("arguments", "{}"),
                            },
                        }
                        for i, tc in enumerate(tool_calls)
                    ],
                })

                for tc in tool_calls:
                    func_name = tc.get("name") or tc.get("function", {}).get("name")
                    raw_args = tc.get("arguments") or tc.get("function", {}).get("arguments", {})
                    args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args)

                    tool_res = execute_agent_tool(session.project_path, session.codebase, func_name, args)

                    if func_name == "apply_patch":
                        if tool_res.get("success"):
                            patch_applied = True
                            rel_path = args.get("file_path") or args.get("path")
                            if rel_path and rel_path not in modified_files:
                                modified_files.append(rel_path)
                            await session.broadcast("patch_applied", {
                                "file": rel_path,
                                "search": args.get("search"),
                                "replace": args.get("replace"),
                            })
                        else:
                            await session.broadcast("patch_failed", {"file": args.get("file_path"), "error": tool_res.get("error")})

                    # Append tool result to messages for next LLM turn
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", "call_0"),
                        "content": json.dumps(tool_res),
                    })

                if patch_applied:
                    break

            if patch_applied:
                patch_diff_text = get_git_diff(session.project_path)
                update_codebase_model(session.project_path, session.codebase, modified_files)

            # ─── STATE 4: VERIFY ───────────────────────────────────────────────
            session.state = "verify"
            await session.broadcast("state_change", {
                "state": "verify",
                "attempt": attempt_num,
                "command": session.initial_command,
            })

            start_t = time.time()
            verify_res = await execute_command(session.initial_command, cwd=session.project_path)
            duration = (time.time() - start_t) * 1000
            session.execution.add_result(verify_res)

            # Log attempt to database
            attempt_record = {
                "attempt_number": attempt_num,
                "state": "success" if verify_res.exit_code == 0 else "verify",
                "error_type": error_type,
                "error_message": error_msg,
                "diagnosis": diagnosis_text,
                "plan": "Apply targeted patch and rerun verification command",
                "patch_diff": patch_diff_text,
                "files_modified": modified_files,
                "command_run": session.initial_command,
                "stdout": verify_res.stdout,
                "stderr": verify_res.stderr,
                "exit_code": verify_res.exit_code,
                "duration_ms": duration,
                "llm_reasoning": diagnosis_text,
            }
            session.attempts.append(attempt_record)

            async with SessionLocal() as db:
                await crud.create_debug_attempt(
                    db,
                    session_id=session.session_id,
                    **attempt_record
                )
                await crud.increment_session_attempts(db, session.session_id)

            # ─── MEMORY: Save fix result to .zen/ ─────────────────────────
            explanation = generate_plain_english_explanation(error_type, error_msg, diagnosis_text, modified_files)
            fix_record = {
                "error_type": error_type,
                "error_message": error_msg,
                "diagnosis": diagnosis_text,
                "why_failed": explanation["why_failed"],
                "what_fixed": explanation["what_fixed"],
                "files_modified": modified_files,
                "patch_diff": patch_diff_text,
                "command": session.initial_command,
                "was_successful": verify_res.exit_code == 0,
                "attempt_number": attempt_num,
            }
            save_fix(session.project_path, fix_record)

            if verify_res.exit_code == 0:
                # Save a context note about what we learned
                add_context_note(
                    session.project_path,
                    f"Fixed {error_type} in {', '.join(modified_files) if modified_files else 'unknown files'}: {explanation['what_fixed']}"
                )

                session.status = "success"
                session.state = "success"
                async with SessionLocal() as db:
                    await crud.update_debug_session_status(db, session.session_id, "success")

                # Broadcast completion with explanation & memory save confirmation
                await session.broadcast("memory_saved", {
                    "message": "Fix saved to .zen/ memory for future reference.",
                    "fix_summary": {
                        "error_type": error_type,
                        "diagnosis": diagnosis_text[:150],
                        "why_failed": explanation["why_failed"],
                        "what_fixed": explanation["what_fixed"],
                        "files_modified": modified_files,
                    },
                })

                await session.broadcast("completed", {
                    "attempt": attempt_num,
                    "message": "Bug fixed! Verification command passed with exit code 0.",
                    "patch_diff": patch_diff_text,
                    "why_failed": explanation["why_failed"],
                    "what_fixed": explanation["what_fixed"],
                    "files_modified": modified_files,
                    "verified_output": verify_res.stdout.strip() if verify_res.stdout else "Exit code 0 (Clean run)",
                })
                break
            else:
                await session.broadcast("verification_failed", {
                    "attempt": attempt_num,
                    "exit_code": verify_res.exit_code,
                    "why_failed": explanation["why_failed"],
                    "stderr": verify_res.stderr,
                })

        return session.status
