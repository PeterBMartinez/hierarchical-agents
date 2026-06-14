#!/usr/bin/env bash
export HOME=/home/peter
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export AGENT_STATE_DIR=/home/peter/hierarchical-agents/dashboard/state
DASH=/home/peter/hierarchical-agents/dashboard
THREAD="$AGENT_STATE_DIR/threads/helm.jsonl"
mkdir -p "$(dirname "$THREAD")"
touch "$THREAD"

agent_model(){ /usr/bin/python3 -c "import json,os;p=os.path.join('$AGENT_STATE_DIR','models.json');d=json.load(open(p)) if os.path.isfile(p) else {};print(d.get('$1') or 'sonnet')" 2>/dev/null || echo sonnet; }

read -r -d '' PROMPT <<'EOF'
You are helm, the orchestrator on the mission-control dashboard. The user just sent you a message. Handle it now, then stop.

STEP 1 — Read your inbox:
   /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py inbox --name helm

STEP 2 — Memory-augmented routing: call qdrant-find BEFORE deciding where to send the task.
   Query: the task text from your inbox.
   Parse the top result for two things:
     a) AGENT CONTINUITY — does the metadata show a specific agent already handled a similar task?
        If yes, prefer routing there — that agent has prior context on this domain.
        In your reply: "Routing to **atlas** — already has context on this topic from [date]."
     b) EXISTING WORK — did an agent already complete this exact task or something very close?
        If yes, surface the prior result to the user instead of re-delegating.
        In your reply: "atlas already researched this on [date]: [1-sentence summary]. Re-sending if you want a fresh pass."
   If memory returns nothing relevant, proceed with role-based routing as normal.

STEP 3 — Decide: answer directly, single-agent delegate, or kick off a PIPELINE.

   SINGLE-AGENT ROUTING — answer directly for status/summaries/quick questions; delegate one specialist for contained tasks.
   Use the AVAILABLE AGENTS roster injected below. Routing priority = memory continuity (STEP 2) first, role fit second.

   PIPELINE ROUTING — use when the task requires research AND content creation:
   Trigger signals: "research X and write a post", "find insights on X for LinkedIn/X thread", "what's new in X — I want to write about it", "turn [topic] into content", or any request that clearly needs both atlas AND brand.
   How to execute a pipeline:
     a) Send to atlas with the pipeline marker appended to the task text:
        Task to atlas: "<research request> [PIPELINE→brand: <one-sentence content brief>]"
        Example: "Research the business impact of AI agent memory systems. [PIPELINE→brand: draft a LinkedIn post on why memory-augmented agents outperform stateless ones, targeting CTOs and engineering leaders]"
     b) Atlas will complete the research then automatically trigger brand with the findings.
     c) You send ONE message to atlas only — do NOT also send to brand. Brand fires automatically.
     d) In your reply to the user: "Pipeline started: atlas is researching → brand will draft once the brief is ready. I'll surface the result when both are done."

   When delegating (pipeline or single-agent), your STEP 5 reply MUST include:
     • What was routed, to whom, and why (role fit + memory continuity if applicable)
     • Whether this is a pipeline ("atlas → brand") or a single-agent task
     Example single: "Sent to **data** — already has Warp 9 metrics from yesterday, will give you a delta."
     Example pipeline: "Pipeline started: **atlas → brand** — atlas will research the topic, brand will turn findings into a draft. Expect two results back."

STEP 4 — ALWAYS send via Bash (never just claim you did):
   /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py send --to <agent> --text "THE FULL TASK" --from helm
   The --from helm flag is REQUIRED on every send. A pipeline still uses a single send to atlas; atlas handles the rest.

STEP 5 — ALWAYS finish by posting one reply to the user:
   /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py reply --name helm --text "YOUR REPLY"

SHARED MEMORY — Write-back after every turn.
  WRITE: After handling a task, call qdrant-store with what was routed and why.
    Content: 2 sentences max — which agent was chosen, why (role fit or memory continuity), any user preference stated.
    Metadata: {"agent": "helm", "type": "episodic"}
  If agent-memory tools are unavailable, skip silently. Never let memory operations delay your reply.

Rules: read-only; do NOT send emails/Teams or modify ClickUp/Azure DevOps. Delegate ONLY via the STEP 3 send command; reply ONLY via the STEP 4 reply command. Be concise.
EOF

process() {
  exec 9>/tmp/helm-watcher.lock
  flock -n 9 || return 0
  PENDING=$(/usr/bin/python3 "$DASH/hermit_chat.py" inbox --name helm 2>/dev/null)
  [ -z "$PENDING" ] && return 0
  [ "$PENDING" = "(no new messages)" ] && return 0
  MODEL=$(agent_model helm); [ -z "$MODEL" ] && MODEL=sonnet

  THREAD_CTX=$(/usr/bin/python3 - <<'PYEOF'
import json, os
base = '/home/peter/hierarchical-agents/dashboard/state/threads'
try:
    idx = os.path.join(base, 'helm', 'index.json')
    conv_id = None
    if os.path.isfile(idx):
        for c in json.load(open(idx)):
            if c.get('active'):
                conv_id = c['id']; break
    path = os.path.join(base, 'helm', conv_id+'.jsonl') if conv_id else os.path.join(base, 'helm.jsonl')
    lines = open(path).readlines() if os.path.isfile(path) else []
    recent = []
    for line in lines[-10:]:
        try:
            m = json.loads(line.strip())
            who = m.get('from') or '?'
            text = (m.get('text') or '').strip().replace('\n', ' ')[:300]
            ts = (m.get('ts') or '')[:16]
            recent.append(f'[{ts}] {who}: {text}')
        except: pass
    print('\n'.join(recent))
except: pass
PYEOF
)

  TODAY=$(date +%F)
  NOW=$(date +"%H:%M %Z")

  AGENT_ROSTER=$(/usr/bin/python3 - <<'PYEOF'
import json, os
agents_dir = '/home/peter/hierarchical-agents/dashboard/state/agents'
roster = []
if os.path.isdir(agents_dir):
    for fname in sorted(os.listdir(agents_dir)):
        if not fname.endswith('.json'):
            continue
        try:
            a = json.load(open(os.path.join(agents_dir, fname)))
            name = a.get('name', '')
            if name == 'helm':
                continue
            role = a.get('role', '')
            desc = a.get('desc', '') or a.get('task', '')
            status = a.get('status', 'unknown')
            roster.append(f"  {name} ({role}) [{status}] — {desc}")
        except:
            pass
print('\n'.join(roster) if roster else '  (no agents registered)')
PYEOF
)

  FULL_PROMPT="${PROMPT}

AVAILABLE AGENTS (live roster — use this when routing or making suggestions):
${AGENT_ROSTER}

Today: ${TODAY} | Time: ${NOW}
RECENT CONVERSATION HISTORY (last 10 messages — use this for context on what has already been said):
${THREAD_CTX}"

  /usr/bin/python3 "$DASH/report.py" --name helm --role Orchestrator --kind orchestrator --status working --task "Working on your request" >/dev/null 2>&1
  timeout 240 claude -p "$FULL_PROMPT" --permission-mode bypassPermissions --model "$MODEL" --max-turns 30 --output-format stream-json --verbose 2>/dev/null | /usr/bin/python3 "$DASH/parse_stream.py" --name helm
  /usr/bin/python3 "$DASH/report.py" --name helm --role Orchestrator --kind orchestrator --status idle --task "Awaiting orders" >/dev/null 2>&1
}

process

if command -v inotifywait >/dev/null 2>&1; then
  while true; do
    inotifywait -q -t 30 -e modify,close_write,moved_to "$THREAD" >/dev/null 2>&1
    sleep 0.4
    process
  done
else
  LAST=""
  while true; do
    SIG=$(stat -c "%Y-%s" "$THREAD" 2>/dev/null)
    [ "$SIG" != "$LAST" ] && { LAST="$SIG"; process; }
    sleep 2
  done
fi
