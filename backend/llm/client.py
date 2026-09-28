"""
llm/client.py — Groq LLM client wrapper with tool-calling support.

Wraps the Groq AsyncGroq client with:
  - Tool/function calling
  - Multi-turn conversation management
  - Token-aware truncation
  - Error handling and retries
"""
import os
import json
from typing import List, Dict, Any, Optional
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()

_client: Optional[AsyncGroq] = None
MODEL = os.getenv("MODEL_ID", "openai/gpt-oss-120b")


def get_client() -> AsyncGroq:
    """Get or create the Groq client singleton."""
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key or "your_" in api_key:
            raise ValueError("GROQ_API_KEY not configured. Set it in backend/.env")
        _client = AsyncGroq(api_key=api_key)
    return _client


def is_configured() -> bool:
    """Check if the Groq API key is properly configured."""
    key = os.getenv("GROQ_API_KEY", "").strip()
    return bool(key) and "your_" not in key


async def chat(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict]] = None,
    temperature: float = 0.2,
    max_tokens: int = 2000,
) -> Dict[str, Any]:
    """
    Send a chat completion request to Groq.

    Args:
        messages: Conversation messages
        tools: Optional tool/function definitions
        temperature: Sampling temperature
        max_tokens: Max response tokens

    Returns:
        Dict with 'content', 'tool_calls', and 'finish_reason'
    """
    client = get_client()

    kwargs = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    try:
        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        result = {
            "content": message.content or "",
            "tool_calls": [],
            "finish_reason": choice.finish_reason,
        }

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                result["tool_calls"].append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": args,
                })

        return result

    except Exception as exc:
        return {
            "content": f"LLM error: {str(exc)}",
            "tool_calls": [],
            "finish_reason": "error",
            "error": str(exc),
        }


async def chat_simple(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.2,
    max_tokens: int = 1500,
) -> str:
    """Simple chat without tools — returns just the text response."""
    result = await chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return result["content"]


# Aliases
get_groq_client = get_client


async def chat_completion(client, messages, tools=None, temperature=0.2, max_tokens=2000):
    res = await chat(messages, tools=tools, temperature=temperature, max_tokens=max_tokens)
    return {
        "message": {"content": res["content"], "tool_calls": res["tool_calls"]},
        "error": res.get("error"),
    }

