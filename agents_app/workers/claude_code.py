import json
import subprocess

from ..config import WORKER_MODEL
from ..worker import Worker

DEFAULT_TOOLS = "Read,Glob,Grep,Edit,Write,Bash"


class ClaudeCodeWorker(Worker):
    def __init__(self, model: str = WORKER_MODEL, allowed_tools: str = DEFAULT_TOOLS) -> None:
        self._model = model
        self._allowed_tools = allowed_tools

    @property
    def name(self) -> str:
        return "claude_code"

    @property
    def description(self) -> str:
        return "Reads, writes, and runs code in the project via the Claude Code CLI."

    def run(self, task: str) -> str:
        completed = subprocess.run(
            [
                "claude",
                "-p",
                task,
                "--output-format",
                "json",
                "--model",
                self._model,
                "--allowedTools",
                self._allowed_tools,
                "--permission-mode",
                "acceptEdits",
            ],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return f"Claude Code worker failed: {completed.stderr.strip()}"
        return _result_text(completed.stdout)


def _result_text(stdout: str) -> str:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout.strip()
    return str(payload.get("result", stdout)).strip()
