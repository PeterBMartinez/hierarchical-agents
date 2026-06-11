import anthropic

from ..config import MAX_TOKENS, WORKER_MODEL
from ..support import text_of
from ..worker import Worker

SYSTEM = """You are a rigorous research analyst.
Investigate the given question across multiple independent sources using web search and fetch.
Cross-check key claims, distrust hype, and note where evidence is thin.
Return a structured, concise findings brief with inline source URLs and clear, actionable takeaways."""

WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]


class ResearcherWorker(Worker):
    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "researcher"

    @property
    def description(self) -> str:
        return "Deep multi-source web research and synthesis for a focused question."

    def run(self, task: str) -> str:
        messages = [{"role": "user", "content": task}]
        while True:
            response = self._client.messages.create(
                model=WORKER_MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM,
                tools=WEB_TOOLS,
                messages=messages,
            )
            if response.stop_reason != "pause_turn":
                return text_of(response)
            messages.append({"role": "assistant", "content": response.content})
