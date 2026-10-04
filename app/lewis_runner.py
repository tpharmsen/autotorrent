import json
import sys
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parents[2] / "agentLewis"
sys.path.insert(0, str(AGENT_ROOT / "src"))

from lewis_agents.config import Settings
from lewis_agents.graph import create_graph


def main() -> None:
    request = json.load(sys.stdin)
    settings = Settings(_env_file=str(AGENT_ROOT / ".env"))
    approve_commands = bool(request.get("approve_commands", False))

    def approve_command(command: str, workspace: Path) -> bool:
        return approve_commands

    graph = create_graph(settings=settings, approve_command=approve_command)
    result = graph.invoke(
        {
            "messages": request["messages"],
            "route": None,
        }
    )
    answer = result["messages"][-1].content
    if not isinstance(answer, str):
        answer = json.dumps(answer)
    print(json.dumps({"answer": answer}))


if __name__ == "__main__":
    main()
