import os


def _model(env_key: str) -> str:
    return os.environ.get(env_key, "claude-opus-4-8")


ORCHESTRATOR_MODEL = _model("ORCHESTRATOR_MODEL")
WORKER_MODEL = _model("WORKER_MODEL")
MAX_TOKENS = int(os.environ.get("AGENT_MAX_TOKENS", "16000"))
OUTPUT_DIR = os.environ.get("AGENT_OUTPUT_DIR", "outputs")
