import hmac
import json
import os
import re
import secrets
import subprocess
import threading
import time
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
OLLAMA_RETRIES = 2
CONFIRMATION_PATTERN = re.compile(
    r"^\s*(?:yes|y|yeah|yep|sure|okay|ok|confirm|confirmed|approved|approve)"
    r"(?:[\s,!.:-]+.*)?$",
    re.IGNORECASE,
)
DECLINE_PATTERN = re.compile(
    r"^\s*(?:no|n|nope|nah|cancel|stop|don't|do not)"
    r"(?:[\s,!.:-]+.*)?$",
    re.IGNORECASE,
)
REPEAT_COMMAND_PATTERN = re.compile(
    r"\b(?:again|rerun|re-run|reexecute|re-execute|repeat|run\s+(?:it|that)\s+again)\b",
    re.IGNORECASE,
)
FIGURE_PATTERN = re.compile(r"fig\d+(?:_red)?\.png")
PLOT_COMMAND_PATTERN = re.compile(r"(?<![\w.-])plot_[\w-]+\.py(?![\w.-])")
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
            "name": "show_figure",
            "description": "Show one generated training, validation, testing or custom figure on the project page. Use the exact filename from the workspace output directory.",
            "parameters": {
                "type": "object",
                "required": ["filename"],
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "A PNG filename such as fig0.png",
                    }
                },
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
You are a careful local software-project assistant called FlowBenchAgent.

Your workspace is {WORKSPACE}. Treat it as the only allowed project scope. Do not
claim to have read, changed, or executed anything unless you used the available
tools and received a result. When a path is unknown, use list_files before
guessing. Use read_file to inspect relevant files before proposing edits.

You may answer questions and inspect the workspace without confirmation. The
show_figure tool can display one existing fig*.png file on the project page when the
user asks to see a specific result.
When a confirmed run_command successfully executes any plotting function or
plot_*.py script, check whether output/fig0.png exists. If it does, it is
automatically placed in the project page figure slot; tell the user that the
figure was refreshed.
write_file and run_command tools always require explicit user confirmation; never
try to bypass that requirement or treat an unrelated message as approval.
Prefer small, targeted edits and preserve existing project conventions. Before
requesting confirmation for a write or command, briefly explain what will happen.
Do not expose access tokens, credentials, or other secrets in your response.

Be concise and direct. After a tool result, explain the result plainly and state
any limitation or error instead of inventing a successful outcome.
Never report a command as executed based only on an earlier result in the
conversation. Every requested execution must call run_command and use its
fresh result.
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


def _show_figure(filename: str) -> str:
    if not FIGURE_PATTERN.fullmatch(filename):
        raise ValueError("Only generated fig*.png files can be shown")
    figure_path = _safe_path(f"output/{filename}")
    if not figure_path.is_file():
        raise ValueError(f"Figure does not exist: output/{filename}")
    return json.dumps({"filename": filename, "modified": figure_path.stat().st_mtime_ns})


def _figure_zero() -> Optional[dict[str, Any]]:
    figure_path = _safe_path("output/fig0.png")
    if not figure_path.is_file():
        return None

    return {
        "filename": figure_path.name,
        "modified": figure_path.stat().st_mtime_ns,
    }


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
    if name == "show_figure":
        return _show_figure(arguments["filename"])
    if name == "write_file":
        return _write_file(arguments["path"], arguments["content"])
    if name == "run_command":
        return _run_command(arguments["command"])
    raise ValueError(f"Unknown tool: {name}")


def _session(token: str) -> dict[str, Any]:
    with _sessions_lock:
        return _sessions.setdefault(token, _new_session_state())


def _new_session_state() -> dict[str, Any]:
    return {"messages": [], "pending_tool": None, "last_command": None}


def reset_chat(token: str) -> None:
    with _sessions_lock:
        _sessions[token] = _new_session_state()


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


def _is_decline(message: str) -> bool:
    return bool(DECLINE_PATTERN.match(message))


def _is_repeat_command_request(message: str) -> bool:
    return bool(REPEAT_COMMAND_PATTERN.search(message))


def _confirmation_prompt(name: str, arguments: dict[str, Any]) -> str:
    if name == "write_file":
        path = arguments.get("path", "?")
        return f"I can update `{path}` in the workspace. Would you like me to go ahead?"
    if name == "run_command":
        command = arguments.get("command", "?")
        return (
            "I can run this command in the workspace:\n\n"
            f"`{command}`\n\n"
            "Would you like me to go ahead?"
        )
    return f"I can use `{name}`. Would you like me to go ahead?"


def _request_ollama(messages: list[dict[str, Any]]) -> requests.Response:
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "tools": TOOLS,
        "messages": messages,
    }
    last_error: Optional[Exception] = None
    for attempt in range(OLLAMA_RETRIES + 1):
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                timeout=120,
            )
            if response.status_code < 500 and response.status_code != 429:
                return response
            last_error = RuntimeError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:500]}"
            )
        except requests.RequestException as exc:
            last_error = exc
        if attempt < OLLAMA_RETRIES:
            time.sleep(0.5 * (attempt + 1))
    raise HTTPException(
        status_code=502,
        detail=f"Ollama is temporarily unavailable: {last_error}",
    )


def _ollama(token: str, message: str, tool_result: Optional[dict[str, Any]] = None) -> dict[str, Any]:
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
    response = _request_ollama(messages)
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {response.text[:500]}")
    try:
        response_body = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Ollama returned invalid JSON") from exc
    assistant = response_body.get("message")
    if not isinstance(assistant, dict):
        raise HTTPException(status_code=502, detail="Ollama response did not contain a message")
    answer = assistant.get("content", "")
    calls = assistant.get("tool_calls") or []
    history.append({"role": "user", "content": message} if not tool_result else {"role": "tool", "content": tool_result["content"]})
    if calls:
        call = calls[0].get("function", {})
        name = call.get("name")
        arguments = call.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=502, detail="Ollama returned invalid tool arguments") from exc
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise HTTPException(status_code=502, detail="Ollama returned an invalid tool call")
        if _tool_requires_confirmation(name):
            state["pending_tool"] = {"name": name, "arguments": arguments}
            return {"answer": _confirmation_prompt(name, arguments)}
        try:
            result = _execute_tool(name, arguments)
        except (KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
            result = f"Tool error: {exc}"
        if name == "show_figure":
            if result.startswith("{"):
                state["selected_figure"] = json.loads(result)
        return _ollama(token, message, {"name": name, "content": result})
    history.append({"role": "assistant", "content": answer})
    return {
        "answer": answer or "I could not produce a response.",
        "figure": state.get("selected_figure"),
    }


def process_chat(token: str, message: str) -> dict[str, Any]:
    state = _session(token)
    state["selected_figure"] = None
    pending = state.get("pending_tool")
    if pending and _is_decline(message):
        state["pending_tool"] = None
        state["messages"].extend(
            [
                {"role": "user", "content": message},
                {"role": "assistant", "content": "Okay, I won't do that."},
            ]
        )
        return {"answer": "Okay, I won't do that."}
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
                    "content": (
                        f"Executed {_tool_summary(pending['name'], pending['arguments'])}.\n\n"
                        f"{result}"
                    ),
                },
            ]
        )
        figure = None
        command = pending["arguments"].get("command", "")
        if pending["name"] == "run_command" and isinstance(command, str):
            state["last_command"] = command
        if (
            pending["name"] == "run_command"
            and PLOT_COMMAND_PATTERN.search(command)
            and result.startswith("exit_code=0")
        ):
            figure = _figure_zero()
            if figure:
                result += f"\nRefreshed project figure: {figure['filename']}"
                history[-1]["content"] += f"\nRefreshed project figure: {figure['filename']}"
        return {
            "answer": f"Executed {_tool_summary(pending['name'], pending['arguments'])}.\n\n{result}",
            "figure": figure,
        }
    last_command = state.get("last_command")
    if (
        isinstance(last_command, str)
        and last_command
        and _is_repeat_command_request(message)
        and not pending
    ):
        state["pending_tool"] = {"name": "run_command", "arguments": {"command": last_command}}
        return {"answer": _confirmation_prompt("run_command", {"command": last_command})}
    return _ollama(token, message)
