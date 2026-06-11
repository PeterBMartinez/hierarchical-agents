# Cost Monitor

A dependency-free guardrail for an always-on Claude Code / hermit agent. It reads
hermit's `.claude/cost-log.jsonl`, totals **today's** spend, and alerts when you
cross a daily budget. Runs on `python3` alone — nothing to install, ideal for a Pi.

## Why first

An always-on agent that hits its limit **fails hard with no fallback and no
alert**. This watches the meter and warns you (and can halt the agent) before that
happens.

## One-time schema check

Field names in `cost-log.jsonl` aren't documented, so the monitor is
schema-adaptive (it tries the common names and picks the most granular record tier
to avoid double-counting). Once hermit has logged anything, confirm it reads the
file correctly:

```bash
python3 cost-monitor/cost_monitor.py --inspect
```

It prints record count, the tiers it found, the tier it selected, today's total,
and a few sample lines. If today's total looks wrong, override the field names via
env (`COST_LOG_PATH`) or tell me the sample lines and I'll tune the parser in one
edit.

## Run

```bash
DAILY_BUDGET_USD=5 python3 cost-monitor/cost_monitor.py
```

Exit codes: `0` = OK or WARN, `1` = OVER budget. Use the exit code to gate the
agent (e.g. stop the hermit container when it returns `1`).

Continuous mode instead of cron:

```bash
python3 cost-monitor/cost_monitor.py --interval 900
```

## Schedule on the Pi (every 15 min)

```bash
# crontab -e
*/15 * * * * cd /home/pi/path/to/work && \
  DAILY_BUDGET_USD=5 COST_ALERT_WEBHOOK_URL=https://your-webhook \
  python3 cost-monitor/cost_monitor.py >> cost-monitor/monitor.log 2>&1
```

## Phone alerts (optional)

Set `COST_ALERT_WEBHOOK_URL` and it POSTs `{"text": ..., "content": ...}` on WARN
and OVER — which works as-is with a **Discord** webhook (`content`), a **Slack**
incoming webhook (`text`), or any custom endpoint. For **ntfy**, point it at a
small relay or ask me to add a raw-body mode.

## Config

| Env | Default | Meaning |
|---|---|---|
| `COST_LOG_PATH` | `.claude/cost-log.jsonl` | Path to hermit's cost log |
| `DAILY_BUDGET_USD` | `5` | Daily spend ceiling |
| `COST_WARN_RATIO` | `0.8` | Warn once spend crosses this fraction of budget |
| `COST_ALERT_WEBHOOK_URL` | _(unset)_ | Optional webhook for WARN/OVER alerts |
