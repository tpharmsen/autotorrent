import hmac
import json
import os
import re
import secrets
import subprocess
import threading
from pathlib import Path
from typing import Any, Optional

import requests
from fastapi import HTTPException
from pydantic import BaseModel


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = Path(
    os.getenv("CHATBOT_WORKSPACE", "/home/tpharmsen/Documents/flowbench-cnn")
).expanduser().resolve()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
TOKEN_PATH = REPO_ROOT / ".chatbot-token"
MAX_OUTPUT_BYTES = 32 * 1024
MAX_READ_BYTES = 256 * 1024
CONFIRMATION_PATTERN = re.compile(
    r"^\s*(?:yes|y|yeah|yep|sure|okay|ok|confirm|confirmed|approved|approve)"
    r"(?:[\s,!.:-]+.*)?$",
    re.IGNORECASE,
)
_sessions: dict[str, dict[str, Any]] = {}
_sessions_lock = threading.Lock()


class ChatbotRequest(BaseModel):
    message: str


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories inside the workspace. Use this instead of guessing paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workspace-relative directory, default ."},
                    "recursive": {"type": "boolean", "description": "List nested entries too"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file inside the workspace.",
            "parameters": {
                "type": "object",
                "required": ["path"],
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or replace a UTF-8 text file inside the workspace. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "required": ["path", "content"],
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command with the workspace as its working directory. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "required": ["command"],
                "properties": {"command": {"type": "string"}},
            },
        },
    },
]

SYSTEM_PROMPT = f"""
You are a careful local software-project assistant.

Your workspace is {WORKSPACE}. Treat it as the only allowed project scope. Do not
claim to have read, changed, or executed anything unless you used the available
tools and received a result. When a path is unknown, use list_files before
guessing. Use read_file to inspect relevant files before proposing edits.

You may answer questions and inspect the workspace without confirmation. The
write_file and run_command tools always require explicit user confirmation; never
try to bypass that requirement or treat an unrelated message as approval.
Prefer small, targeted edits and preserve existing project conventions. Before
requesting confirmation for a write or command, briefly explain what will happen.
Do not expose access tokens, credentials, or other secrets in your response.

Be concise and direct. After a tool result, explain the result plainly and state
any limitation or error instead of inventing a successful outcome.
""".strip()


def _get_token() -> str:
    configured = os.getenv("CHATBOT_TOKEN")
    if configured:
        return configured
    try:
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        token = secrets.token_urlsafe(32)
        TOKEN_PATH.write_text(token + "\n", encoding="utf-8")
        print(f"[chatbot] generated token; read it from {TOKEN_PATH}")
        try:
            TOKEN_PATH.chmod(0o600)
        except OSError:
            pass
    if not token:
        raise RuntimeError("CHATBOT_TOKEN is empty")
    return token


def require_chatbot_token(provided: Optional[str]) -> None:
    if not provided or not hmac.compare_digest(provided, _get_token()):
        raise HTTPException(status_code=401, detail="Invalid chatbot token")


def _safe_path(path: str) -> Path:
    candidate = (WORKSPACE / (path or ".")).resolve()
    try:
        candidate.relative_to(WORKSPACE)
    except ValueError as exc:
        raise ValueError("Path must stay inside the chatbot workspace") from exc
    return candidate


def _list_files(path: str = ".", recursive: bool = False) -> str:
    directory = _safe_path(path)
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {path}")
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    entries = []
    for entry in sorted(iterator):
        if len(entries) >= 500:
            entries.append("... listing truncated at 500 entries ...")
            break
        suffix = "/" if entry.is_dir() else ""
        entries.append(str(entry.relative_to(WORKSPACE)) + suffix)
    return "\n".join(entries) or "(empty directory)"


def _read_file(path: str) -> str:
    file_path = _safe_path(path)
    if not file_path.is_file():
        raise ValueError(f"Not a file: {path}")
    if file_path.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"File is larger than {MAX_READ_BYTES} bytes")
    return file_path.read_text(encoding="utf-8")


def _write_file(path: str, content: str) -> str:
    file_path = _safe_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {file_path.relative_to(WORKSPACE)}"


def _run_command(command: str) -> str:
    result = subprocess.run(
        ["/bin/bash", "-lc", command],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    output = (result.stdout + result.stderr)[:MAX_OUTPUT_BYTES]
    return f"exit_code={result.returncode}\n{output}".strip()


def _execute_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "list_files":
        return _list_files(arguments.get("path", "."), arguments.get("recursive", False))
    if name == "read_file":
        return _read_file(arguments["path"])
    if name == "write_file":
        return _write_file(arguments["path"], arguments["content"])
    if name == "run_command":
        return _run_command(arguments["command"])
    raise ValueError(f"Unknown tool: {name}")


def _session(token: str) -> dict[str, Any]:
    with _sessions_lock:
        return _sessions.setdefault(token, {"messages": [], "pending_tool": None})


def _tool_requires_confirmation(name: str) -> bool:
    return name in {"write_file", "run_command"}


def _tool_summary(name: str, arguments: dict[str, Any]) -> str:
    if name == "write_file":
        return f"write_file({arguments.get('path', '?')})"
    if name == "run_command":
        return f"run_command({arguments.get('command', '?')})"
    return name


def _is_confirmation(message: str) -> bool:
    """Accept natural confirmation messages without treating arbitrary text as approval."""
    return bool(CONFIRMATION_PATTERN.match(message))


def _ollama(token: str, message: str, tool_result: Optional[dict[str, Any]] = None) -> str:
    state = _session(token)
    history = state["messages"]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
    if tool_result:
        messages.append(
            {
                "role": "tool",
                "tool_name": tool_result["name"],
                "content": tool_result["content"],
            }
        )
    else:
        messages.append({"role": "user", "content": message})
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": OLLAMA_MODEL, "stream": False, "tools": TOOLS, "messages": messages},
        timeout=120,
    )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {response.text[:500]}")
    assistant = response.json().get("message", {})
    answer = assistant.get("content", "")
    calls = assistant.get("tool_calls") or []
    history.append({"role": "user", "content": message} if not tool_result else {"role": "tool", "content": tool_result["content"]})
    if calls:
        call = calls[0].get("function", {})
        name = call.get("name")
        arguments = call.get("arguments", {})
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if _tool_requires_confirmation(name):
            state["pending_tool"] = {"name": name, "arguments": arguments}
            return f"I want to run `{_tool_summary(name, arguments)}`. Reply `yes` to confirm."
        result = _execute_tool(name, arguments)
        return _ollama(token, message, {"name": name, "content": result})
    history.append({"role": "assistant", "content": answer})
    return answer or "I could not produce a response."


def process_chat(token: str, message: str) -> str:
    state = _session(token)
    pending = state.get("pending_tool")
    if pending and _is_confirmation(message):
        state["pending_tool"] = None
        try:
            result = _execute_tool(pending["name"], pending["arguments"])
        except (KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired, requests.RequestException) as exc:
            result = f"Tool error: {exc}"

        # The server has already received the confirmation, so do not send the
        # action back through Ollama for a second approval request.
        history = state["messages"]
        history.extend(
            [
                {"role": "user", "content": message},
                {
                    "role": "assistant",
                    "content": f"Executed {_tool_summary(pending['name'], pending['arguments'])}.",
                },
                {"role": "tool", "content": result},
            ]
        )
        return f"Executed {_tool_summary(pending['name'], pending['arguments'])}.\n\n{result}"
    return _ollama(token, message)
