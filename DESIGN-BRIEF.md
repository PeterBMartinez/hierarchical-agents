# Agent Operations Center — Design Brief

## What This Is

A personal mission-control dashboard for an AI agent team. The user (a delivery manager) has three AI agents running 24/7 on a Raspberry Pi. He can open the dashboard on any device, see what the agents are doing in real time, chat with them directly, and monitor open work items across his projects.

Think of it like a cross between a chat application (Slack), a server monitoring dashboard (Datadog), and a command center — but the "team" being managed is a group of AI agents, not humans.

---

## The Three Agents

| Agent | Personality | What It Does |
|-------|-------------|-------------|
| **helm** | The captain. Routes and coordinates. | Receives all user messages first. Decides whether to answer directly or hand the task to a specialist. Always replies to the user. |
| **atlas** | The researcher. Thorough and methodical. | Handles research tasks. Saves findings to Notion and returns a link. |
| **ops** | The delivery coordinator. Operational and concise. | Tracks delivery work across multiple software projects. Reads PR queues, work items, comms. Knows when things are overdue. |

---

## Screens / Views

### 1. Main Dashboard (always visible)

The default view. Three horizontal zones stacked vertically:

**A. Banner (top, conditional)**
Only shows when there are open tasks on the Notion To-Do board. Displays up to 10 items as a horizontal scrolling strip. Items are color-coded by priority (High = red, Medium = yellow). Hidden entirely when no active items exist.

**B. Header**
- Product name / identity ("AGENT CONTROL")
- Live metrics: how many agents are currently working, today's AI API cost, current time
- Clicking the cost metric opens the Analytics overlay

**C. Body (two columns)**
- **Left column: Crew Roster** — a vertical list of the three agents. Each card shows agent name, role, current status (idle / working / planning / error), what task they're doing right now, and when they last updated. Clicking any card opens the Inspector panel.
- **Right column: Facility Map** — a visual representation of all three agents as animated robot characters at workbenches. The orchestrator (helm) is larger and centered. Worker agents are in a row below. Robots animate when working (arm moves, screen flickers), sleep when idle. Below the map is a scrolling event ticker showing the last few dozen status events as a live feed.

---

### 2. Inspector Panel (slides in from the right when an agent is clicked)

Opens as a third column on desktop, full-screen on mobile. Contains the agent name at the top with a close button. Four tabs:

**OVERVIEW tab**
Agent status card: current status, role, type, model, last active time. Two stat boxes: tasks started today vs completed today.

**ACTIVITY tab**
A timestamped log of every status change for this agent — working, done, idle, error. Shows the last 80 events.

**TUNE tab**
- Model selector: three buttons (Haiku / Sonnet / Opus) with cost indicators. Clicking changes the model this agent uses on its next run.
- Quick directive buttons: pre-written instructions like "Summarize today", "Go deeper", "Be frugal". Clicking sends it to the agent's inbox.
- Free-text directive input for custom instructions.

**COMMS tab**
The main chat interface. This is where the user talks to agents. Split into two sub-areas:

- **Left sidebar: Conversation list** — a narrow column showing all past conversations with this agent. Each entry has a title (auto-generated from the first message) and a relative timestamp. A `+ NEW CHAT` button at the top starts a fresh conversation. Hovering shows a delete button. Active conversation is highlighted.
- **Right main area: Message thread** — the selected conversation's messages, newest at bottom. Agent messages render with full markdown (tables, bold, code blocks, links). User messages are plain text. A text input + send button at the bottom.

---

### 3. Analytics Overlay (opens over everything)

Full-screen modal. Shows:
- Cost for today / this week / this month
- Cost breakdown by agent (bar chart)
- Activity count by agent today

---

## Agent States and What They Mean Visually

Every agent and every event in the system has one of five statuses:

| Status | Color (current) | Meaning |
|--------|----------------|---------|
| `idle` | Teal/dim | Agent is online, not doing anything |
| `working` | Amber/yellow | Agent is actively running a Claude session |
| `planning` | Purple | Agent is in a planning or coordination phase |
| `done` | Green | Last task completed successfully |
| `error` | Red/pink | Something went wrong |

These statuses drive:
- The left border color on roster cards
- The glow color on map robot cells
- The color of event entries in the ticker and activity log

---

## Data That Updates Live

The dashboard polls the server every 2 seconds. The following change dynamically:

- Agent status and current task (shows up immediately when an agent starts/stops a run)
- The event ticker (new entries appear as agents report in)
- The active/online count in the header
- The cost figure
- The banner (new To-Do items appear hourly from the Notion scan)
- The message thread in COMMS (new agent replies appear as they're written)

---

## Constraints for the Designer

**Must keep:**
- Single-file HTML — all CSS and JS inline, no build step, no external dependencies except the two fonts and marked.js (CDN)
- The polling model (2-second tick), so the UI must handle rapid state refreshes without jarring redraws
- The five agent statuses must remain visually distinct — they carry real meaning
- Mobile must work: the layout collapses to single column, the inspector becomes full-screen, the conversation sidebar becomes a horizontal scroll strip
- The overall layout zones (banner / header / roster + map / inspector) must remain conceptually intact
- Dark background is a practical constraint (runs on OLED/dim screens, always-on Pi display)

**Can completely change:**
- The cyberpunk / terminal aesthetic — fonts, color palette, borders, glows, animations
- The robot character visualization — could be replaced with anything that communicates agent state (status rings, activity waveforms, abstract shapes, literal icons, etc.)
- Typography — currently IBM Plex Mono + Orbitron; any pairing that reads clearly at small sizes works
- Card layouts and spacing
- The event ticker — currently a horizontal marquee; could be a vertical feed, toast notifications, etc.
- Banner design — currently a horizontal pill strip; could be cards, a sidebar, an icon badge, etc.
- The COMMS tab — currently minimal; could have avatar-style message bubbles, agent profile headers, typing indicators, etc.

**Things the designer should be aware of:**
- Agent names are short lowercase strings: `helm`, `atlas`, `ops`
- Task descriptions can be 1–3 sentences of natural language
- Message content in COMMS is markdown — the renderer supports tables, code blocks, bold, italic, lists, and links
- The cost metric shows a dollar figure like `$1.24` — it can be large or small depending on the day
- The banner is intentionally attention-grabbing — it represents real open work items that need the user's attention

---

## Suggested Focus Areas for the Redesign

1. **Agent identity** — each agent currently looks identical except for name/status. Consider giving helm, atlas, and ops distinct visual identities (color signature, icon, or illustration) that carry through the roster, map, inspector header, and COMMS tab.

2. **Status communication** — the current glow + color system works but is subtle. The redesign could make working/error states more dramatic so the user notices immediately at a glance.

3. **COMMS tab** — this is the highest-frequency interaction surface. Currently very minimal. Could become a proper chat UI with message bubbles, timestamps in-line, agent avatar on replies, and a more polished conversation list.

4. **Map visualization** — the pixel-robot animation is a design choice that can be completely replaced. What matters is that working agents look different from idle ones, and the hierarchy (helm at top, workers below) is clear.

5. **Banner** — currently always the same amber strip. Could be more contextual — urgency level could change the visual weight of the whole banner.

---

## Technical Format for Handoff

The final redesign should be delivered as a single updated `dashboard/index.html` file (or a set of annotated mockups + CSS variables to swap in). The designer can treat the existing file as a template — all the HTML structure and JS logic stays the same; only the CSS and visual markup (SVGs, class names for styling) needs to change.

Key CSS custom properties that currently drive the color system (good candidates to redesign around):

```css
--bg          /* page background */
--panel       /* card/panel background */
--line        /* border/separator color */
--ink         /* primary text */
--dim         /* secondary/muted text */
--chrome      /* accent / interactive highlight */
--idle        /* status: idle */
--planning    /* status: planning */
--working     /* status: working */
--done        /* status: done */
--error       /* status: error */
--glow        /* box-shadow shorthand for glow effects */
```

Swapping these 11 variables alone will retheme the entire dashboard.
