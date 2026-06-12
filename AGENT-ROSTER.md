# Agent Roster — Possibilities

## What Others Are Doing (Research Summary)

Before the roster, the honest picture from researching what successful engineers and entrepreneurs are actually running:

**The credible patterns:**
- **Andrej Karpathy**: 10–20 parallel coding agents, zero manual code since Dec 2025. Built "Dobby" — a WhatsApp-connected home automation agent. Created AutoResearch, which ran 700 ML experiments over 2 days automatically (now called "The Karpathy Loop" — loop of propose→measure→commit if improved).
- **Tobias Lütke (Shopify CEO)**: Applied the Karpathy Loop to Shopify's templating engine — 120 overnight experiments, 53% faster output.
- **Simon Willison**: 95% AI-generated code, works from his iPhone, 4 parallel agents. Saves reusable prompts ("hoarding") as core practice.
- **Pieter Levels**: Solo founder, vibe-codes AI products ($3.5M+ ARR), <$200/month infra. Automation is the business model — he's not managing people, he's managing agents.
- **Greg Isenberg**: Markets the idea of "ContextCaddy" — an agent that shadows you all day, reads your emails and meetings, builds a context file you can query anytime.
- **James Wang**: Morning briefing agent on Claude Code with 6 MCP connectors (Gmail, Google Calendar, HubSpot, OmniFocus, note apps). Runs via cron, zero interaction needed.

**The honest caveat:** Most "AI agents" described publicly are workflow automations with an LLM in one step — not truly autonomous. The agents that work reliably in production are the ones with clear triggers, bounded scope, and a defined output format. That's exactly the architecture already running here.

**Tools the builder community uses:** n8n (workflow orchestration), Claude Code (coding + long-context tasks), MCP servers (integration layer), Supabase (agent memory/RAG), GitHub Actions (scheduling), tmux (always-on sessions).

---

## Current Agents (Live on pi-02)

| Agent | Kind | Role | Trigger |
|-------|------|------|---------|
| **helm** | orchestrator | Routes all user requests; delegates to atlas or ops | inotifywait (message-driven) |
| **atlas** | hermit | Research tasks; saves findings to Notion | inotifywait (message-driven) |
| **ops** | coordinator | Delivery tracking across Aria, TruckSpy, Warp 9; reads PRs, work items, comms | cron every 3 min |

---

## Proposed Agents

---

### 1. brand — Personal Brand Agent
**Priority: High**

The most immediately useful addition given the LinkedIn + X growth goal.

**What it does:**
- Draft LinkedIn posts and X threads on a given topic or product update — two variants per request, in your voice, saved to a Notion "Content Queue" for your review before anything is posted
- Weekly engagement report: pull post performance from LinkedIn and X (impressions, reactions, replies), summarize what's resonating, surface any comments needing a reply
- Campaign planning: given a product brief, produce a full campaign plan in Notion — target audience, key messages, content types, posting cadence, launch timeline

**Trigger:** Message-driven (helm delegates to it) + weekly scheduled engagement scan

**Tools needed:**
- Notion (already have) — for content queue and campaign plans
- LinkedIn API + MCP server — limited for personal accounts; may require starting with draft-only until API access is established
- X/Twitter API — more accessible; free tier allows posting and reading basic metrics

**Start with:** Draft-only (no API required). You write the topic, brand drafts it to Notion, you copy-paste and post. Add the API connectors for posting and engagement monitoring once the drafts workflow is solid.

**Validated by:** Multiple indie hackers running n8n + Claude content pipelines. Pieter Levels distributes all his products through his own Twitter audience — content is infrastructure for him.

---

### 2. dev — Engineering Agent
**Priority: High**

You build products. This agent runs experiments and reviews code while you're doing other things.

**What it does:**
- **Karpathy Loop on your own projects**: given a clear goal with a measurable outcome (performance, test pass rate, bundle size), runs batched experiments overnight — proposes a change, measures it, commits only if improved, loops
- **PR review**: when you open a PR on any of your own projects, dev reviews it for correctness, security, and style; posts a summary to your ops inbox or the dashboard banner
- **Spec-to-draft**: describe a feature, dev writes a first implementation and opens a draft PR for you to review
- **Debugging**: paste an error or failing test, dev proposes and applies the fix

**Trigger:** Message-driven (user or helm delegates) + optional webhook from GitHub on PR open

**Tools needed:**
- GitHub MCP (read repos, create PRs, post comments)
- File system access (already available via Claude Code)
- Shell execution (already available)

**No new infrastructure needed.** This is exactly what Claude Code already does — it just needs a watcher and a prompt file like helm/atlas.

**Validated by:** This is the most proven agent pattern in existence. Karpathy, Willison, Lütke — all running this. The December 2025 model quality inflection made it reliable.

---

### 3. learn — Knowledge Agent
**Priority: Medium**

Manages your reading queue and builds a searchable second brain.

**What it does:**
- **Read queue**: you send it URLs or paste article text; it summarizes, extracts key points, and saves a structured note to a Notion "Knowledge Base"
- **Weekly digest**: every Monday morning, produces a summary of everything saved that week with connections to other notes
- **Topic deep-dives**: you ask "what do I know about X" and it searches your Notion knowledge base, synthesizes across all saved notes, and gives you a brief
- **Auto-tagging and linking**: when saving new content, it checks existing notes and adds cross-references

**Trigger:** Message-driven + weekly scheduled digest

**Tools needed:**
- Notion (already have) — for storing notes
- Web fetch (already available via Claude Code)
- cluster-rag MCP (already have on pi-02) — could index your own notes for faster RAG search

**Validated by:** Simon Willison's "prompt hoarding" practice is essentially this. James Wang saves all his Substack reading via an agent pipeline. Multiple builders use Obsidian + Claude Code for a second brain — Notion works the same way with the MCP connector you already have.

---

### 4. product — Product Agent
**Priority: Medium**

For the products you build. Tracks metrics, maintains roadmap, handles user feedback triage.

**What it does:**
- **Metrics monitoring**: checks product analytics (revenue, signups, churn, active users) on a schedule; flags anomalies in the banner
- **Roadmap maintenance**: maintains a Notion roadmap page; when you send it a feature idea, it adds it with priority, effort estimate, and user impact
- **Feedback triage**: reads incoming feedback (email, form submissions, GitHub issues); categorizes, prioritizes, and adds actionable items to the roadmap
- **Launch checklists**: given a product launch date, generates a checklist in Notion (marketing, technical, support)

**Trigger:** Message-driven + daily scheduled metrics check

**Tools needed:**
- Notion (already have)
- Analytics API (depends on your stack — Plausible, PostHog, Stripe all have APIs and MCP servers)
- Email/GitHub MCP (for feedback ingestion)

**Note:** Scope this tightly to products you own. Client projects stay in ops.

---

### 5. net — Network Agent
**Priority: Low-Medium**

Relationship management without a CRM.

**What it does:**
- **Follow-up reminders**: you tell it "I met Sarah at the conference, follow up in 2 weeks about the partnership idea" — it adds a reminder and pings you in the banner when due
- **Contact context**: before a meeting, you ask it to pull everything you know about the person — past conversations, shared notes, public content they've posted
- **Warm-up drafts**: drafts a re-engagement message for a contact you haven't spoken to in a while, in your voice, to your Notion queue

**Trigger:** Message-driven

**Tools needed:**
- Notion (already have) — contact notes database
- Possibly a simple contacts MCP or just structured Notion pages

**Validated by:** Greg Isenberg's "ContextCaddy" concept exactly. He describes this as the agent he'd build first for any founder.

---

## Priority Order for Building

| Order | Agent | Reason |
|-------|-------|--------|
| 1 | **brand** | Immediate use case, clear output (Notion drafts), no API blocker for v1 |
| 2 | **dev** | Highest leverage — multiplies everything you build; no new infrastructure |
| 3 | **learn** | High daily value; trivial to build on existing Notion + atlas patterns |
| 4 | **product** | Depends on having live products with metrics to monitor |
| 5 | **net** | Lower urgency; can be added once the core roster is humming |

---

## What the Research Suggests You Skip (For Now)

- **Finance/deal flow agents**: Only valuable if you're actively doing M&A or managing a portfolio. High setup cost for current use case.
- **Customer support agents**: Only when a product has meaningful inbound support volume.
- **Sales/outreach agents**: Only if you're running outbound — not relevant yet.
- **Separate social media scheduler**: Don't add another automation layer. brand handles content creation; you post manually or add API access later. Keeping the human in the loop on what actually goes out is the right call for a personal brand.

---

## Architecture Note

All proposed agents follow the same pattern already running:

```
trigger (cron or inotifywait)
  → check inbox / condition
  → build prompt + conversation context
  → claude -p with relevant MCP tools
      → agent does work
      → saves output to Notion
      → replies via hermit_chat.py
  → report status to dashboard
```

helm routes to all of them. The dashboard shows all of them. No new infrastructure needed for any agent on this list.
