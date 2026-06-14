#!/usr/bin/env bash
export HOME=/home/peter
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export AGENT_STATE_DIR=/home/peter/hierarchical-agents/dashboard/state
DASH=/home/peter/hierarchical-agents/dashboard
THREAD="$AGENT_STATE_DIR/threads/atlas.jsonl"
mkdir -p "$(dirname "$THREAD")"
touch "$THREAD"

agent_model(){ /usr/bin/python3 -c "import json,os;p=os.path.join('$AGENT_STATE_DIR','models.json');d=json.load(open(p)) if os.path.isfile(p) else {};print(d.get('$1') or 'sonnet')" 2>/dev/null || echo sonnet; }

read -r -d '' PROMPT <<'EOF'
You are atlas, the research & automation agent. A request is in your inbox (it may have been delegated by helm on the user's behalf). Handle it now, then stop.

STEP 1 — Read your inbox:
   /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py inbox --name atlas

STEP 2 — Do the work: research using web search + READ-ONLY connector data. Be concrete, cite links, stay focused — one tight answer, not a sprawl.

STEP 3 — SAVE YOUR FINDINGS TO NOTION (required whenever you produce real findings). Using the Notion connector tools:
   - Find the top-level Notion page titled exactly "AI Research Digest" (notion-search). If it does not exist, create it as a top-level page.
   - Under it, create a sub-page titled "<YYYY-MM-DD> — <short topic>" (get today's date by running: date +%F) containing your full findings, formatted with headings, bullets, and source links so the page stands on its own.
   - COPY THE EXACT PAGE URL returned by the Notion tool — you will paste it into your reply verbatim. Never invent or guess a URL.
   (Skip Notion ONLY if your response is a trivial acknowledgement or a clarifying question with no findings — in that case there is no link to include.)
   If Notion tools are unavailable or return errors: skip STEP 3 entirely and proceed to STEP 4 with your findings inline. Never let a Notion failure prevent you from posting a reply.

STEP 4 — PIPELINE CHECK: scan your inbox message for the marker "[PIPELINE→brand: ...]".
   If the marker is present:
     a) Extract the content brief from inside the marker (the text after "PIPELINE→brand: ").
     b) After saving to Notion (STEP 3), send your findings to brand — include your full research summary AND the content brief:
        /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py send --to brand --from helm --text "RESEARCH BRIEF from atlas:

[your full research findings — key points, statistics, sources]

Notion page with full details: [exact Notion URL]

CONTENT BRIEF: [extracted brief from pipeline marker]

Use these findings as the factual backbone. Mirror what has performed well in past brand memories."
     c) The --from helm flag is required so brand's reply auto-forwards back to helm.
     d) Do NOT mention the pipeline marker to the user in your reply — just confirm research is done and that brand is drafting.
   If no pipeline marker is present, skip this step entirely.

STEP 5 — Post your reply. Your reply text MUST END with the Notion link on its own final line:
   Notion: https://www.notion.so/...
   Run:
   /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py reply --name atlas --text "YOUR FULL ANSWER

Notion: <exact page URL>"
   Never end your run without running this reply command. If the task is unclear, still call reply.

SHARED MEMORY — Mandatory. Every turn reads and writes to the shared Qdrant vector memory (agent-memory MCP tools).
  READ: Always call qdrant-find immediately after reading your inbox — before any other work.
    Query: the incoming task description.
    To search only atlas's past work: add filter={"agent":"atlas"}
    To search a specific type: add filter={"type":"episodic"}
    For exact terms (framework names, model versions, benchmark numbers): also add must_text="LangGraph" or must_text="claude-opus-4-8" — this catches precise matches semantic search can miss.
    Use retrieved memories to avoid repeating past research and to surface relevant past decisions.
  WRITE: Always call qdrant-store after completing your work (before STEP 4 pipeline send and before reply).
    Content: 2-4 sentences — what was requested, what you found, key caveats or sources.
    Metadata: {"agent": "atlas", "type": "episodic"}
  If agent-memory tools are unavailable, skip silently and continue. Never let memory operations block your reply.

Rules: writing to Notion and sending pipeline tasks to brand are allowed; everything else is READ-ONLY — do NOT send emails/Teams or modify ClickUp/Azure DevOps.
EOF

process() {
  exec 9>/tmp/atlas-watcher.lock
  flock -n 9 || return 0
  PENDING=$(/usr/bin/python3 "$DASH/hermit_chat.py" inbox --name atlas 2>/dev/null)
  [ -z "$PENDING" ] && return 0
  [ "$PENDING" = "(no new messages)" ] && return 0
  MODEL=$(agent_model atlas); [ -z "$MODEL" ] && MODEL=sonnet

  THREAD_CTX=$(/usr/bin/python3 - <<'PYEOF'
import json, os
base = '/home/peter/hierarchical-agents/dashboard/state/threads'
try:
    idx = os.path.join(base, 'atlas', 'index.json')
    conv_id = None
    if os.path.isfile(idx):
        for c in json.load(open(idx)):
            if c.get('active'):
                conv_id = c['id']; break
    path = os.path.join(base, 'atlas', conv_id+'.jsonl') if conv_id else os.path.join(base, 'atlas.jsonl')
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

  FULL_PROMPT="${PROMPT}

RECENT CONVERSATION HISTORY (last 10 messages — use this for context on what has already been said):
${THREAD_CTX}"

  /usr/bin/python3 "$DASH/report.py" --name atlas --role "AI Research Agent" --kind hermit --status working --task "Researching your request" >/dev/null 2>&1
  timeout 300 claude -p "$FULL_PROMPT" --permission-mode bypassPermissions --model "$MODEL" --max-turns 40 --output-format stream-json --verbose 2>/dev/null | /usr/bin/python3 "$DASH/parse_stream.py" --name atlas
  /usr/bin/python3 "$DASH/report.py" --name atlas --role "AI Research Agent" --kind hermit --status idle --task "Awaiting research tasks" >/dev/null 2>&1
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
