"""
zen_chat.py — Conversational Zen agent + Mem0 memory graph.

This module wraps the legacy learning agent and exposes a stable memory API for the
chat UI and graph page. It gracefully falls back when Mem0 is unavailable.
"""
import importlib.util
import os
from pathlib import Path

from memory.chat_store import get_chat_store


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


def _fetch_raw_items(client, session_id: str) -> list:
    """Read raw memory items from whichever backend is active.

    mem0 >= 2.0 rejects top-level entity kwargs on get_all() and requires
    filters={'user_id': ...}; earlier releases accepted user_id directly.
    """
    if client is None or isinstance(client, str):
        return []

    res = None
    if hasattr(client, "get_all"):
        try:
            res = client.get_all(filters={"user_id": session_id})
        except (TypeError, ValueError):
            # Older mem0 / alternate clients.
            res = client.get_all(user_id=session_id)
    elif hasattr(client, "search"):
        res = client.search(
            query="user preferences facts lessons habits",
            user_id=session_id,
            limit=50,
        )

    if isinstance(res, dict) and "results" in res:
        return res["results"] or []
    if isinstance(res, list):
        return res
    return []


def list_user_memories(session_id: str) -> list:
    """Return normalized memory nodes for a user."""
    client = _get_memory_client()

    try:
        items = _fetch_raw_items(client, session_id)
    except Exception as err:
        # Logged (not swallowed) — a silent failure here is what made the
        # memory graph render empty for every user.
        print(f"Memory list error: {type(err).__name__}: {err}")
        return []

    nodes = []
    seen_ids = set()
    for i, raw in enumerate(items):
        node = _normalize_memory_item(raw, i)
        if not node:
            continue
        # Guard against duplicate/missing ids breaking React keys and edges.
        if node["id"] in seen_ids:
            node["id"] = f"{node['id']}-{i}"
        seen_ids.add(node["id"])
        nodes.append(node)
    return nodes


def save_user_memories(session_id: str, texts: list) -> dict:
    """Persist conversation text into long-term memory.

    Idempotent: memories already stored (or already forwarded upstream) are not
    re-sent, so the client can safely post its whole message list each time.
    """
    cleaned = [t.strip() for t in (texts or []) if isinstance(t, str) and t.strip()]
    if not cleaned:
        return {"saved": 0, "skipped": 0, "total": 0}

    client = _get_memory_client()
    report = {"saved": 0, "skipped": 0, "total": len(cleaned)}

    # Upstream mem0: only forward what it has not already been given.
    if client is not None and not isinstance(client, str):
        store = get_chat_store()
        try:
            fresh = store.filter_unforwarded(session_id, cleaned)
            report["skipped"] = len(cleaned) - len(fresh)
            for text in fresh:
                try:
                    client.add(
                        messages=[{"role": "user", "content": text}],
                        user_id=session_id,
                    )
                    store.mark_forwarded(session_id, [text])
                    report["saved"] += 1
                except Exception as err:
                    print(f"Memory add error: {type(err).__name__}: {err}")
        except Exception as err:
            print(f"Memory save error: {type(err).__name__}: {err}")
        return report

    # SQLite store: it owns dedup internally.
    store = get_chat_store()
    try:
        store.add(messages=[{"role": "user", "content": t} for t in cleaned], user_id=session_id)
        report["saved"] = len(cleaned)
    except Exception as err:
        print(f"Memory save error: {type(err).__name__}: {err}")
    return report


def build_memory_graph(session_id: str) -> dict:
    """Build a node/edge graph of a user's memories.

    Edges combine a chronological chain (consecutive memories, labelled
    "related") with keyword-similarity links (labelled "similar").
    """
    nodes = list_user_memories(session_id)
    edges = []
    edge_ids = set()

    def add_edge(src, tgt, label):
        edge_id = f"e-{src}->{tgt}"
        if edge_id in edge_ids or src == tgt:
            return
        edge_ids.add(edge_id)
        edges.append({"id": edge_id, "source": src, "target": tgt, "label": label})

    # Chronological chain.
    for i in range(1, len(nodes)):
        add_edge(nodes[i - 1]["id"], nodes[i]["id"], "related")

    # Similarity links across a sliding window.
    def keywords(text):
        return {w.strip(".,!?;:()[]\"'").lower() for w in text.split() if len(w) > 4}

    for i, a in enumerate(nodes):
        words_a = keywords(a["text"])
        if not words_a:
            continue
        for j in range(i + 1, min(i + 5, len(nodes))):
            b = nodes[j]
            if len(words_a & keywords(b["text"])) >= 2:
                add_edge(a["id"], b["id"], "similar")

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


# Messages that look like something worth remembering long-term.
_MEMORY_TRIGGERS = (
    "my name is", "i am", "i'm", "remember that", "i prefer", "i like",
    "i work", "call me", "my favourite", "my favorite", "i use", "i live",
)


def _remember(user_id: str, message: str):
    """Best-effort durable save of a noteworthy user message."""
    lower = message.lower()
    if len(message) >= 400 or not any(t in lower for t in _MEMORY_TRIGGERS):
        return
    try:
        save_user_memories(user_id, [message.strip()])
    except Exception as err:
        print(f"Memory save error: {type(err).__name__}: {err}")


async def chat_with_zen(user_id: str, message: str, history=None) -> dict:
    history = history or []
    memories = get_user_memories(user_id)
    memory_context = ""
    if memories:
        # get_user_memories() returns plain strings (already unwrapped from
        # mem0's dicts), but tolerate dicts too rather than crashing the whole
        # chat with a TypeError if that contract ever changes.
        texts = []
        for m in memories:
            if isinstance(m, dict):
                m = m.get("text") or m.get("memory") or ""
            if isinstance(m, str) and m.strip():
                texts.append(m.strip())
        if texts:
            memory_context = "Things you remember about this user:\n" + "\n".join(
                f"- {m}" for m in texts[:8]
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

    # Store the message before generating a reply, so nothing is lost if the
    # LLM is unavailable or errors out.
    _remember(user_id, message)

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    is_placeholder = not groq_key or "your_groq_api_key" in groq_key or groq_key == "dummy"

    if is_placeholder:
        reply = (
            "I'm Zen. Connect a GROQ_API_KEY in your backend `.env` for full replies. "
            "Until then, I can still store memories in the local memory store."
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

    return {"reply": reply, "memories_used": len(memories)}
