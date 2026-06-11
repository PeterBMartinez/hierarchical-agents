# Hierarchical Agents

A custom, self-owned **orchestrator → worker** agent system built on the official
Anthropic Python SDK. An orchestrator decomposes a goal, delegates subtasks to
specialized worker agents, and synthesizes their results into one answer.

It runs anywhere Python (or Docker) runs — your Mac, or a Raspberry Pi on your
Tailscale network — and you own every line.

## Topology

```
 goal ─▶ Orchestrator ─┬─ delegate_to_researcher ──▶ Researcher   (web_search + web_fetch)
                       ├─ delegate_to_business_ops ─▶ Business-Ops (plan / draft / save)
                       └─ delegate_to_claude_code ──▶ Claude Code  (read/write/run code)  [opt-in]
                       ◀── integrated answer + next steps
```

- **Orchestrator** (`orchestrator.py`) — routes work; never does specialist work itself.
- **Researcher** (`workers/researcher.py`) — multi-source web research, cross-checked, cited.
- **Business-Ops** (`workers/business_ops.py`) — planning, drafting, saving deliverables.
- **Claude Code** (`workers/claude_code.py`) — wraps the Claude Code CLI; opt-in.
- **Worker** (`worker.py`) — the abstraction every worker implements.

Each worker gets a **fresh, isolated context** and a self-contained task — it
cannot see the other workers or the main conversation. This mirrors Anthropic's
own multi-agent research architecture.

## Is this scalable? (what the research says)

This design follows the orchestrator-worker pattern Anthropic documented in
[How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system):
a lead agent plans, spins up specialized subagents with isolated context, and
synthesizes their results. Two best practices are baked in here:

- **Detailed, self-contained delegation.** The orchestrator gives every worker a
  clear objective, the expected output format, and scope boundaries — the single
  biggest factor in stopping workers from duplicating or gapping work.
- **Asymmetric models = the cost lever.** Anthropic's data shows a capable
  orchestrator paired with *cheaper* workers (e.g. Opus + Haiku) can beat
  Opus-alone (≈87% vs ≈75%) at a fraction of the token cost. This is the main way
  to keep spend bounded.

Set it in `.env`:

```
ORCHESTRATOR_MODEL=claude-opus-4-8     # planning + synthesis
WORKER_MODEL=claude-sonnet-4-6         # the bulk of the tokens — cheaper here
```

(Drop workers to `claude-haiku-4-5` for the cheapest fan-out.)

Multi-agent runs cost more tokens than a single chat — the win is quality and
parallelizable throughput, not cheapness. Keep each goal scoped to one objective.

## Setup

```bash
cd hierarchical-agents
python -m venv .venv && source .venv/bin/activate
pip install -U -r requirements.txt
cp .env.example .env          # add your real ANTHROPIC_API_KEY
set -a; source .env; set +a
```

## Run

```bash
python -m agents_app.runner "Research the strongest agentic AI patterns right now, then draft a plan to apply them to my work this month"
```

Deliverables land in `outputs/`.

## Live dashboard (mission deck)

A dependency-free dashboard visualizes the swarm: the master orchestrator in a
central room, worker/hermit agents arranged around it, a live event ticker, and a
spend gauge. See [`dashboard/README.md`](dashboard/README.md).

```bash
AGENT_STATE_DIR=dashboard/state DAILY_BUDGET_USD=5 python3 dashboard/server.py
# open http://localhost:8787  (or http://<pi-tailscale-ip>:8787 from your phone/TV)
```

Run a goal in another terminal and the rooms light up live. Any agent type can
appear on the board, including hermits — they self-report via `dashboard/report.py`.

## Run in Docker (deploy anywhere)

```bash
docker compose up -d dashboard                       # the mission deck on :8787
docker compose run --rm agents "Research X, then draft a plan for Y"   # run a goal
```

The `dashboard` service is long-running; the `agents` service is a one-shot CLI
(under the `cli` profile) that shares the `dashboard/state` volume, so its agents
appear on the deck in real time. `.env` is loaded for both. The image bundles Node +
the Claude Code CLI so the opt-in worker runs in-container; delete that block in the
`Dockerfile` to slim the image. The dashboard mounts `./.claude` read-only for the
cost gauge — point `COST_LOG_PATH` at your real hermit cost log.

## The Claude Code worker (opt-in)

`workers/claude_code.py` wraps `claude -p "<task>" --output-format json` and
parses the returned `result`. Because it implements the same `Worker` interface,
it plugs in with **no orchestrator changes**. Enable it with
`ENABLE_CLAUDE_CODE_WORKER=1` in `.env`. It gives the team a worker that can
actually read, edit, and run code in the project.

**Billing — read this.** Driven headlessly, Claude Code can authenticate two ways:

- `ANTHROPIC_API_KEY` → per-token API billing (predictable for servers).
- `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) → draws on your **Max
  subscription**. Note: per Anthropic, from **June 15, 2026** subscription-driven
  `claude -p` / Agent SDK usage draws from a *separate monthly Agent SDK credit*,
  not your interactive limits. See the
  [headless docs](https://code.claude.com/docs/en/headless).

In Docker, pass whichever token via `.env`. Avoid `--dangerously-skip-permissions`;
this worker uses `--permission-mode acceptEdits` with an explicit allowed-tools list.

## Add a worker (no orchestrator changes to the others)

1. Create `workers/<name>.py` with a class implementing `Worker`.
2. Register it in `runner.py`'s `build_orchestrator`.
3. Add a guarded `delegate_to_<name>` tool in `orchestrator.py`.

## Next scaling steps

- **Parallel fan-out.** Today delegations run one at a time. For real concurrency,
  move to `AsyncAnthropic` and dispatch independent workers with
  `asyncio.gather()` — the largest throughput win.
- **A verifier worker.** Add an adversarial critic that checks the researcher's
  claims before the orchestrator trusts them.
- **Hooks + observability.** Log every delegation and add OpenTelemetry tracing
  before running unattended in production.

## Sources

- [How we built our multi-agent research system — Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Run Claude Code programmatically (headless) — Claude Code Docs](https://code.claude.com/docs/en/headless)
- [Claude Agent SDK overview — Claude Code Docs](https://code.claude.com/docs/en/agent-sdk/overview)
