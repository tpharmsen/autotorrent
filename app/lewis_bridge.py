import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_ROOT = (REPO_ROOT.parent / "agentLewis").resolve()
AGENT_PYTHON = Path(
    os.getenv("LEWIS_PYTHON", str(AGENT_ROOT / ".venv" / "bin" / "python"))
)
RUNNER = Path(__file__).with_name("lewis_runner.py")


class AgentMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=100_000)


class LewisRequest(BaseModel):
    messages: list[AgentMessage] = Field(min_length=1, max_length=50)
    approve_commands: bool = False


def _run(request: LewisRequest) -> dict[str, str]:
    payload = {
        "messages": [message.model_dump() for message in request.messages],
        "approve_commands": request.approve_commands,
    }
    try:
        completed = subprocess.run(
            [str(AGENT_PYTHON), str(RUNNER)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=AGENT_ROOT,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise RuntimeError(detail[-2_000:])
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Lewis returned invalid JSON") from exc
    if not isinstance(response, dict) or not isinstance(response.get("answer"), str):
        raise RuntimeError("Lewis returned an invalid response")
    return response


async def run_lewis(request: LewisRequest) -> dict[str, str]:
    return await asyncio.to_thread(_run, request)
