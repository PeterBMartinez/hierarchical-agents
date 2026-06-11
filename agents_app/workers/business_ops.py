from pathlib import Path

import anthropic
from anthropic import beta_tool

from ..config import MAX_TOKENS, WORKER_MODEL
from ..support import output_path, text_of
from ..worker import Worker

SYSTEM = """You are an operations and productivity specialist.
Turn the given objective into concrete plans, structured task lists, drafts, and decisions.
Persist any finished deliverable with the save_deliverable tool.
Read supporting material with read_local_file when a path is provided.
Be specific and action-oriented; prefer doing over describing."""


@beta_tool
def save_deliverable(filename: str, content: str) -> str:
    """Write a finished deliverable to the outputs directory.

    Args:
        filename: Target file name, for example plan.md.
        content: Full text to write.
    """
    path = output_path(filename)
    path.write_text(content)
    return f"Saved {path}"


@beta_tool
def read_local_file(path: str) -> str:
    """Read a local text file and return its contents.

    Args:
        path: Path to a readable text file.
    """
    target = Path(path)
    if not target.is_file():
        return f"No file at {path}"
    return target.read_text()


class BusinessOpsWorker(Worker):
    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "business_ops"

    @property
    def description(self) -> str:
        return "Planning, task structuring, drafting, and operations execution."

    def run(self, task: str) -> str:
        runner = self._client.beta.messages.tool_runner(
            model=WORKER_MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            tools=[save_deliverable, read_local_file],
            messages=[{"role": "user", "content": task}],
        )
        last = None
        for message in runner:
            last = message
        return text_of(last)
