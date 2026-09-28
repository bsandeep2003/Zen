"""
llm/prompts.py — System prompts and tool definitions for the debugging agent.

Contains all prompt templates and the tool schema that the LLM uses
to interact with the codebase and terminal.
"""


# ─── Tool definitions (Groq function-calling format) ─────────────────────────

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file in the project. Use this to understand code before making changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file from the project root (e.g. 'src/main.py')"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path in the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path (e.g. 'src/' or '.')"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for a text pattern across all source files in the project. Returns matching lines with file paths and line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The text pattern to search for"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Optional glob to filter files (e.g. '*.py')"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_symbol",
            "description": "Find where a function, class, or variable is defined in the codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The symbol name to find (e.g. 'parse_config', 'DatabaseModel')"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "Apply a targeted text replacement to a file. Searches for the exact 'search' text and replaces it with 'replace' text. Prefer small, targeted patches over rewriting entire files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the file to modify"
                    },
                    "search": {
                        "type": "string",
                        "description": "The exact text to find in the file (must match exactly)"
                    },
                    "replace": {
                        "type": "string",
                        "description": "The replacement text"
                    }
                },
                "required": ["file_path", "search", "replace"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path for the new file"
                    },
                    "content": {
                        "type": "string",
                        "description": "The file content"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command in the project directory and return its output. Use this to run tests, build, or verify fixes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_git_diff",
            "description": "Get the current git diff showing all uncommitted changes.",
            "parameters": {
                "type": "object",
                "properties": {},
            }
        }
    },
]


# ─── System prompts ──────────────────────────────────────────────────────────

DIAGNOSE_SYSTEM_PROMPT = """You are Zen, an expert autonomous debugging agent. Your job is to analyze errors, understand root causes, and fix code.

You have access to tools to read files, search code, apply patches, and run commands.

## Your Workflow

1. **Understand the error**: Read the error message carefully. Identify the error type, location, and likely cause.
2. **Gather context**: Use read_file and search_code to understand the relevant code. Don't guess — read the actual files.
3. **Diagnose**: Determine the root cause based on evidence.
4. **Fix**: Apply the smallest possible patch that fixes the issue. Prefer targeted edits over file rewrites.
5. **Verify**: After applying patches, you can run_command to verify the fix works.

## Rules

- Always read relevant files BEFORE modifying them
- Apply the SMALLEST possible fix — don't refactor or rewrite unnecessarily
- If you're unsure, gather more context with read_file and search_code
- Prefer search-and-replace patches over creating entire files
- When applying patches, the 'search' text must EXACTLY match what's in the file
- Explain your reasoning clearly

## Error Analysis Checklist

Before modifying code, determine:
1. What command failed?
2. What is the error type? (SyntaxError, ImportError, TypeError, etc.)
3. What file and line is involved?
4. What function/class is involved?
5. What imports or dependencies are relevant?
6. What recently changed?
7. What is the smallest plausible fix?

## Response Format

After you finish using tools, provide a brief summary:
- **Diagnosis**: What was wrong
- **Fix**: What you changed
- **Files Modified**: List of files you modified"""


def build_debug_prompt(
    error_text: str,
    command: str,
    codebase_summary: str,
    relevant_files: list[str],
    previous_attempts: list[dict],
    file_contents: dict[str, str],
) -> str:
    """
    Build the user message for a debug request.
    Provides structured context without sending the entire codebase.
    """
    parts = []

    # 1. The error
    parts.append(f"## Failed Command\n```\n{command}\n```")
    parts.append(f"## Error Output\n```\n{error_text[:3000]}\n```")

    # 2. Project summary
    parts.append(f"## Project Context\n{codebase_summary}")

    # 3. Relevant files (pre-loaded)
    if file_contents:
        parts.append("## Relevant Files (pre-loaded)")
        for path, content in file_contents.items():
            # Truncate very large files
            if len(content) > 3000:
                content = content[:1500] + f"\n\n... [{len(content) - 3000} chars truncated] ...\n\n" + content[-1500:]
            parts.append(f"### {path}\n```\n{content}\n```")

    # 4. Previous attempts
    if previous_attempts:
        parts.append("## Previous Debug Attempts (DO NOT repeat these)")
        for att in previous_attempts[-3:]:
            parts.append(
                f"- Attempt {att.get('attempt_number', '?')}: "
                f"Error: {att.get('error_message', 'unknown')[:200]} | "
                f"Fix: {att.get('diagnosis', 'unknown')[:200]}"
            )

    # 5. File list
    if relevant_files:
        parts.append(f"## Files likely involved\n{', '.join(relevant_files)}")

    return "\n\n".join(parts)


# Aliases for agent core compatibility
SYSTEM_PROMPT_AGENT = DIAGNOSE_SYSTEM_PROMPT
DEBUGGER_TOOLS = AGENT_TOOLS

