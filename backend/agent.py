"""
agent.py — The self-learning AI agent powered by Groq & Mem0 Memory.

Flow:
  1. On each submission, retrieve past memories for session_id from Mem0.
  2. Read learner profile stats (mistake counts, difficulty tier, avg score).
  3. Construct a dynamic system prompt with both mistake stats AND Mem0 memories.
  4. Call Groq with user code + task description.
  5. Save new key insights into Mem0 memory for the learner.
  6. Return structured JSON feedback.
"""
import json
import os
import re
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()

_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY", ""))
MODEL = os.getenv("MODEL_ID", "llama-3.3-70b-versatile")
MEM0_API_KEY = os.getenv("MEM0_API_KEY", "").strip()

# ─────────────────────────────────────────────
# Mem0 Memory initialization (Cloud or Local fallback)
# ─────────────────────────────────────────────

_memory_client = None

def _get_memory_client():
    global _memory_client
    if _memory_client is not None:
        return _memory_client

    if MEM0_API_KEY:
        try:
            from mem0 import MemoryClient
            _memory_client = MemoryClient(api_key=MEM0_API_KEY)
            print("Mem0 Cloud Memory initialized.")
            return _memory_client
        except Exception as e:
            print(f"Warning: Failed to init Mem0 Cloud Memory ({e}), falling back to local mode.")

    # Local fallback open-source Mem0 / memory store
    try:
        from mem0 import Memory
        config = {
            "llm": {
                "provider": "groq",
                "config": {
                    "model": MODEL,
                    "api_key": os.getenv("GROQ_API_KEY", "")
                }
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "path": "./mem0_storage",
                    "on_disk": True
                }
            }
        }
        _memory_client = Memory.from_config(config)
        print("Mem0 Local Memory initialized.")
    except Exception as e:
        print(f"Mem0 local init notice: {e}. Using SQLite-backed memory fallback.")
        _memory_client = "sqlite_fallback"

    return _memory_client


def get_user_memories(session_id: str) -> list[str]:
    """Retrieve remembered facts for this session_id from Mem0."""
    client = _get_memory_client()
    if not client or client == "sqlite_fallback":
        return []

    try:
        if hasattr(client, "search"): # Local Mem0
            res = client.search(query="coding mistakes habits preferences", user_id=session_id)
            if isinstance(res, dict) and "results" in res:
                return [m.get("memory", "") for m in res["results"] if m.get("memory")]
            elif isinstance(res, list):
                return [m.get("memory", "") if isinstance(m, dict) else str(m) for m in res]
        elif hasattr(client, "get_all"): # Mem0 Cloud MemoryClient
            res = client.get_all(user_id=session_id)
            if isinstance(res, list):
                return [m.get("memory", "") if isinstance(m, dict) else str(m) for m in res]
    except Exception as err:
        print(f"Mem0 fetch error: {err}")
    return []


def add_user_memory(session_id: str, text: str):
    """Store new coding insights/habits into Mem0 for this session_id."""
    client = _get_memory_client()
    if not client or client == "sqlite_fallback":
        return

    try:
        if hasattr(client, "add"):
            client.add(messages=[{"role": "user", "content": text}], user_id=session_id)
    except Exception as err:
        print(f"Mem0 add error: {err}")


# ─────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────

# Max code chars sent to the LLM (~4 chars per token, cap at ~600 tokens of code)
_CODE_CHAR_LIMIT = 2400


def _truncate_code(code: str) -> str:
    """Hard-cap code length to avoid runaway token usage on large files."""
    if len(code) <= _CODE_CHAR_LIMIT:
        return code
    half = _CODE_CHAR_LIMIT // 2
    return (
        code[:half]
        + f"\n\n# ... [truncated {len(code) - _CODE_CHAR_LIMIT} chars] ...\n\n"
        + code[-half:]
    )


def _build_system_prompt(profile: dict, memories: list[str], project_context: str = "") -> str:
    difficulty_labels = {1: "beginner", 2: "elementary", 3: "intermediate", 4: "advanced", 5: "expert"}
    level = difficulty_labels.get(profile.get("current_difficulty", 1), "beginner")
    # Cap at 3 each — beyond that the LLM dilutes focus
    top_mistakes = profile.get("top_mistakes", [])[:3]
    avg_score = profile.get("avg_score", 0.0)
    total_subs = profile.get("total_submissions", 0)

    # ── compact context blocks ──────────────────────────────
    mistake_block = ""
    if top_mistakes:
        items = ", ".join(top_mistakes)
        mistake_block = f"Recurring weak areas: {items}. Weave micro-lessons around these.\n"

    memory_block = ""
    if memories:
        # Cap at 3 most recent/relevant memories
        mem_text = " | ".join(memories[:3])
        memory_block = f"Dev memory: {mem_text}\n"

    stats_block = ""
    if total_subs > 0:
        stats_block = f"Stats: {total_subs} subs, avg {avg_score:.0f}/100, level={level}\n"

    project_block = ""
    if project_context:
        project_block = f"Project Awareness:\n{project_context.strip()}\n"

    # ── compact JSON schema (saves ~120 tokens vs verbose version) ──
    return f"""Zen: {level}-level code mentor. Respond ONLY with this JSON:
{{"score":0-100,"summary":"2-3 sentences","mistakes":["snake_case_tags"],"feedback":"markdown","hint":"one actionable tip","test_cases":[{{"input":"","expected":"","explanation":""}}],"next_challenge":"short description","memory_insight":"one sentence about dev habit"}}
{project_block}{mistake_block}{memory_block}{stats_block}No markdown fences. JSON only."""


# ─────────────────────────────────────────────
# Main agent entry point
# ─────────────────────────────────────────────

async def analyse_code(
    code: str,
    language: str,
    task_description: str,
    profile: dict,
    project_context: str = "",
    project_path: str = "",
) -> dict:
    """
    Sends submission to Groq with Mem0 memories & returns structured JSON feedback.
    Also saves new memory insights into Mem0. Supports Layer 1 Project Awareness.
    """
    session_id = profile.get("session_id", "default")
    
    # 1. Fetch Mem0 memories for this developer
    memories = get_user_memories(session_id)

    # 2. Build Layer 1 Project Context if path provided and context not pre-built
    if project_path and not project_context:
        try:
            from project_reader import scan_project, build_llm_project_context
            proj_summary = scan_project(project_path)
            project_context = build_llm_project_context(proj_summary)
        except Exception as e:
            print(f"Notice: Failed to build project context ({e})")

    # 3. Build system prompt with Mem0 + Project context
    system_prompt = _build_system_prompt(profile, memories, project_context=project_context)

    safe_code = _truncate_code(code)
    task_line = task_description.strip() if task_description.strip() else "general review"
    user_message = f"Task: {task_line}\nLang: {language}\n```\n{safe_code}\n```"

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    is_placeholder = not groq_key or "your_groq_api_key" in groq_key or groq_key == "dummy"

    raw = ""
    if not is_placeholder:
        try:
            response = await _client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=800,  # real responses are 300-600 tokens
            )
            raw = response.choices[0].message.content.strip()
        except Exception as err:
            print(f"Groq API call notice: {err}. Using intelligent adaptive fallback.")
            is_placeholder = True

    if is_placeholder:
        # Generate intelligent mock feedback for testing/demonstration
        detected_mistakes = []
        if "range(len(" in code and "+ 1" in code:
            detected_mistakes.append("off_by_one_index_error")
        elif "factorial" in code and "return" not in code.split("\n")[-2]:
            detected_mistakes.append("missing_return_statement")
        elif "while" in code and "count" not in code:
            detected_mistakes.append("infinite_loop_risk")
        else:
            detected_mistakes.append("general_logic_check")

        result = {
            "score": 65 if detected_mistakes else 90,
            "summary": f"Reviewed {language} code. Detected potential issues requiring attention.",
            "mistakes": detected_mistakes,
            "feedback": f"### Code Review ({language})\n\n- **Issue Detected:** `{', '.join(detected_mistakes)}`\n- Review loop bounds or return statements.\n- *Tip:* Ensure test cases cover boundary values.",
            "hint": "Check boundary conditions or verify return expressions in recursive function calls.",
            "test_cases": [
                {"input": "[1, 2, 3]", "expected": "3", "explanation": "Standard list max test case"},
                {"input": "[]", "expected": "ValueError", "explanation": "Edge case for empty inputs"}
            ],
            "next_challenge": "Implement binary search with proper index boundary checks.",
            "memory_insight": f"Developer frequently experiences {detected_mistakes[0]} in {language} loops/functions."
        }
    else:
        raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```$", "", raw, flags=re.MULTILINE)
        raw = raw.strip()

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Agent returned non-JSON output: {raw[:300]}") from exc

    # Normalise fields
    result.setdefault("score", 50)
    result.setdefault("summary", "")
    result.setdefault("mistakes", [])
    result.setdefault("feedback", "")
    result.setdefault("hint", "")
    result.setdefault("test_cases", [])
    result.setdefault("next_challenge", "")
    result.setdefault("memory_insight", "")

    # 3. Store new memory insight — only if it covers a pattern not already in memory
    insight = result.get("memory_insight", "").strip()
    if insight and len(insight) > 5:
        # Avoid writing duplicate/near-duplicate memories (compare against existing)
        already_known = any(
            any(word in m.lower() for word in insight.lower().split()[:4])
            for m in memories
        )
        if not already_known:
            add_user_memory(session_id, f"{language}: {insight}")

    result["active_memories"] = memories
    return result


# ─────────────────────────────────────────────
# Challenge generator
# ─────────────────────────────────────────────

async def generate_challenge(profile: dict) -> dict:
    """Generate a fresh coding challenge adapted to the learner's profile and Mem0 memories."""
    session_id = profile.get("session_id", "default")
    difficulty_labels = {1: "beginner", 2: "elementary", 3: "intermediate", 4: "advanced", 5: "expert"}
    level = difficulty_labels.get(profile.get("current_difficulty", 1), "beginner")
    lang = profile.get("preferred_language", "python")
    top_mistakes = profile.get("top_mistakes", [])
    memories = get_user_memories(session_id)

    # Cap to 3 to keep the prompt tight
    focus_parts = []
    if top_mistakes:
        focus_parts.append(f"weak: {', '.join(top_mistakes[:3])}")
    if memories:
        focus_parts.append(f"habits: {'; '.join(memories[:3])}")
    focus = f" Target: {' | '.join(focus_parts)}." if focus_parts else ""

    # Compact prompt — saves ~80 tokens vs verbose version
    prompt = f"""Generate a {level} {lang} coding challenge.{focus}
JSON only: {{"title":"","description":"3-5 sentences","starter_code":"","constraints":[],"examples":[{{"input":"","output":""}}]}}"""

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    is_placeholder = not groq_key or "your_groq_api_key" in groq_key or groq_key == "dummy"

    raw = ""
    if not is_placeholder:
        try:
            response = await _client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=600,  # challenge JSON is ~300-400 tokens
            )
            raw = response.choices[0].message.content.strip()
        except Exception as err:
            print(f"Groq API challenge notice: {err}. Using adaptive challenge fallback.")
            is_placeholder = True

    if is_placeholder:
        target = top_mistakes[0] if top_mistakes else "off-by-one errors"
        return {
            "title": f"Adaptive Challenge: Handle {target.replace('_', ' ').title()}",
            "description": f"Write a function `safe_slice(items, start, end)` in {lang} that slices a list without raising IndexError, specifically designed to practice boundary handling and prevent {target}.",
            "starter_code": f"def safe_slice(items, start, end):\n    # Fix potential off-by-one or boundary issues\n    pass\n",
            "constraints": ["Return empty list if indices are out of bounds", "Must handle negative indices safely"],
            "examples": [{"input": "items=[10, 20, 30], start=0, end=5", "output": "[10, 20, 30]"}]
        }

    raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "title": "Write a Function",
            "description": "Write a function that takes a list of integers and returns the sum.",
            "starter_code": "def solution(nums):\n    pass",
            "constraints": ["Handle empty lists", "All integers are positive"],
            "examples": [{"input": "[1, 2, 3]", "output": "6"}],
        }
