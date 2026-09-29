"""
zen_chat.py — Conversational Zen agent + Mem0 memory graph.

This module wraps the legacy learning agent and exposes a stable memory API for the
chat UI and graph page. It gracefully falls back when Mem0 is unavailable.
"""
import importlib.util
import os
from pathlib import Path


def _load_learning_agent():
    path = Path(__file__).resolve().parent / "agent.py"
    spec = importlib.util.spec_from_file_location("zen_learning_agent", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_la = _load_learning_agent()

get_user_memories = _la.get_user_memories
add_user_memory = _la.add_user_memory
_get_memory_client = _la._get_memory_client
_client = _la._client
MODEL = _la.MODEL


def _normalize_memory_item(raw, index: int = 0):
    if isinstance(raw, str):
        text = raw.strip()
        mem_id = f"mem-{index}"
        created = None
    elif isinstance(raw, dict):
        text = (raw.get("memory") or raw.get("text") or raw.get("content") or "").strip()
        mem_id = str(raw.get("id") or raw.get("memory_id") or f"mem-{index}")
        created = raw.get("created_at") or raw.get("updated_at")
    else:
        text = str(raw).strip()
        mem_id = f"mem-{index}"
        created = None

    if not text:
        return None

    kind = "lesson" if len(text.split()) > 12 else "fact"
    return {
        "id": mem_id,
        "text": text,
        "kind": kind,
        "created_at": created,
    }


def list_user_memories(session_id: str) -> list:
    client = _get_memory_client()
    if not client or client == "sqlite_fallback":
        return []

    items = []
    try:
        if hasattr(client, "get_all"):
            res = client.get_all(user_id=session_id)
            if isinstance(res, dict) and "results" in res:
                items = res["results"]
            elif isinstance(res, list):
                items = res
        elif hasattr(client, "search"):
            res = client.search(
                query="user preferences facts lessons habits",
                user_id=session_id,
                limit=50,
            )
            if isinstance(res, dict) and "results" in res:
                items = res["results"]
            elif isinstance(res, list):
                items = res
    except Exception as err:
        print(f"Mem0 list error: {err}")

    nodes = []
    for i, raw in enumerate(items):
        node = _normalize_memory_item(raw, i)
        if node:
            nodes.append(node)
    return nodes


def build_memory_graph(session_id: str) -> dict:
    nodes = list_user_memories(session_id)
    edges = []
    for i in range(1, len(nodes)):
        edges.append({
            "id": f"e-{i}",
            "source": nodes[i - 1]["id"],
            "target": nodes[i]["id"],
            "label": "related",
        })

    for i, a in enumerate(nodes):
        words_a = set(w.lower() for w in a["text"].split() if len(w) > 4)
        for j in range(i + 1, min(i + 4, len(nodes))):
            b = nodes[j]
            words_b = set(w.lower() for w in b["text"].split() if len(w) > 4)
            if len(words_a & words_b) >= 2:
                edge_id = f"e-{a['id']}-{b['id']}"
                if not any(e["id"] == edge_id for e in edges):
                    edges.append({
                        "id": edge_id,
                        "source": a["id"],
                        "target": b["id"],
                        "label": "similar",
                    })

    return {
        "nodes": nodes,
        "edges": edges,
        "memory_count": len(nodes),
        "connection_count": len(edges),
    }


ZEN_CHAT_SYSTEM = """You are Zen, a warm and capable self-learning AI assistant.
You remember past conversations via long-term memory (mem0) and improve over time.
Be concise, helpful, and honest. When you learn something important about the user
(preferences, goals, facts), you may note it internally for future chats.
Do not pretend to have memories you were not given in context."""


async def chat_with_zen(user_id: str, message: str, history=None) -> dict:
    history = history or []
    memories = get_user_memories(user_id)
    memory_context = ""
    if memories:
        memory_context = "Things you remember about this user:\n" + "\n".join(
            f"- {m['text']}" for m in memories[:8]
        )

    messages = [{"role": "system", "content": ZEN_CHAT_SYSTEM}]
    if memory_context:
        messages.append({"role": "system", "content": memory_context})
    for turn in history[-12:]:
        role = turn.get("role", "user")
        if role in ("user", "assistant"):
            content = (turn.get("content") or "").strip()
            if content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message.strip()})

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    is_placeholder = not groq_key or "your_groq_api_key" in groq_key or groq_key == "dummy"

    if is_placeholder:
        reply = (
            "I'm Zen. Connect a GROQ_API_KEY in your backend `.env` for full replies. "
            "Until then, I can still store memories once Mem0 is configured."
        )
        if memories:
            reply += f"\n\nI currently have {len(memories)} memory snippet(s) about you."
        return {"reply": reply, "memories_used": len(memories)}

    try:
        response = await _client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.6,
            max_tokens=900,
        )
        reply = (response.choices[0].message.content or "").strip()
    except Exception as err:
        print(f"Zen chat error: {err}")
        return {
            "reply": "I hit a temporary issue while generating the response. Please try again.",
            "memories_used": len(memories),
        }

    lower = message.lower()
    triggers = ("my name is", "i am", "i'm", "remember that", "i prefer", "i like", "i work")
    if any(t in lower for t in triggers) and len(message) < 400:
        add_user_memory(user_id, message.strip())

    return {"reply": reply, "memories_used": len(memories)}
