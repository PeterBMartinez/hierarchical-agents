import os
import sys

import anthropic

from .orchestrator import Orchestrator
from .workers.business_ops import BusinessOpsWorker
from .workers.researcher import ResearcherWorker


def build_orchestrator(client: anthropic.Anthropic) -> Orchestrator:
    workers = [ResearcherWorker(client), BusinessOpsWorker(client)]
    if os.environ.get("ENABLE_CLAUDE_CODE_WORKER") == "1":
        from .workers.claude_code import ClaudeCodeWorker

        workers.append(ClaudeCodeWorker())
    return Orchestrator(client, workers)


def read_goal(argv: list[str]) -> str:
    if len(argv) > 1:
        return " ".join(argv[1:])
    return sys.stdin.read().strip()


def main() -> None:
    goal = read_goal(sys.argv)
    if not goal:
        raise SystemExit("Provide a goal as an argument or on stdin.")
    client = anthropic.Anthropic()
    orchestrator = build_orchestrator(client)
    print(orchestrator.run(goal))


if __name__ == "__main__":
    main()
