import anthropic
from anthropic import beta_tool

from .activity import report, run_reported
from .config import MAX_TOKENS, ORCHESTRATOR_MODEL, WORKER_MODEL
from .support import text_of
from .worker import Worker

SYSTEM = """You are the orchestrator of a hierarchical agent team.
Decompose the user's goal into independent subtasks and delegate each to the right specialist worker.
When you delegate, give the worker a complete, self-contained instruction: a clear objective,
the exact output format you expect back, and explicit boundaries on scope.
Workers cannot see each other or this conversation, so never assume shared context.
Prefer fanning work out across workers over doing specialist work yourself.
Integrate the workers' results into a single coherent answer with clear next steps."""


class Orchestrator:
    def __init__(self, client: anthropic.Anthropic, workers: list[Worker]) -> None:
        self._client = client
        self._workers = {worker.name: worker for worker in workers}

    def run(self, goal: str) -> str:
        report("orchestrator", "planning", goal, ORCHESTRATOR_MODEL)
        try:
            result = self._run(goal)
        except Exception:
            report("orchestrator", "error", goal, ORCHESTRATOR_MODEL)
            raise
        report("orchestrator", "idle", goal, ORCHESTRATOR_MODEL)
        return result

    def _run(self, goal: str) -> str:
        runner = self._client.beta.messages.tool_runner(
            model=ORCHESTRATOR_MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            tools=self._delegation_tools(),
            messages=[{"role": "user", "content": goal}],
        )
        last = None
        for message in runner:
            last = message
        return text_of(last)

    def _delegation_tools(self) -> list:
        workers = self._workers
        tools = []

        if "researcher" in workers:

            @beta_tool
            def delegate_to_researcher(task: str) -> str:
                """Delegate a focused research question to the researcher worker.

                Args:
                    task: A self-contained research question stating the objective,
                        the desired output format, and any scope boundaries.
                """
                return run_reported(workers["researcher"], task, WORKER_MODEL)

            tools.append(delegate_to_researcher)

        if "business_ops" in workers:

            @beta_tool
            def delegate_to_business_ops(task: str) -> str:
                """Delegate a planning or operations task to the business-ops worker.

                Args:
                    task: A self-contained instruction stating the objective,
                        the desired deliverable and its format, and any scope boundaries.
                """
                return run_reported(workers["business_ops"], task, WORKER_MODEL)

            tools.append(delegate_to_business_ops)

        if "claude_code" in workers:

            @beta_tool
            def delegate_to_claude_code(task: str) -> str:
                """Delegate a coding or filesystem task to the Claude Code worker.

                Args:
                    task: A self-contained instruction to read, write, or run code,
                        stating the objective and the expected result.
                """
                return run_reported(workers["claude_code"], task, WORKER_MODEL)

            tools.append(delegate_to_claude_code)

        return tools
