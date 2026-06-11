import json
import os
import sys
import time
import urllib.request
from datetime import datetime

LOG_PATH = os.environ.get("COST_LOG_PATH", ".claude/cost-log.jsonl")
DAILY_BUDGET_USD = float(os.environ.get("DAILY_BUDGET_USD", "5"))
WARN_RATIO = float(os.environ.get("COST_WARN_RATIO", "0.8"))
WEBHOOK_URL = os.environ.get("COST_ALERT_WEBHOOK_URL")

COST_FIELDS = ["estimated_cost_usd", "cost_usd", "total_cost_usd", "usd", "cost"]
DATE_FIELDS = ["date", "day", "timestamp", "ts", "time", "created_at"]
TIER_FIELDS = ["type", "kind", "scope", "level"]
TIER_PRIORITY = [
    "call",
    "per_call",
    "message",
    "request",
    "turn",
    "session",
    "day",
    "daily",
    "rollup",
]


def read_records(path):
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def _to_date(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).date().isoformat()
    text = str(value).strip()
    if not text:
        return None
    head = text[:10]
    try:
        datetime.strptime(head, "%Y-%m-%d")
        return head
    except ValueError:
        return None


def record_date(record):
    for field in DATE_FIELDS:
        if field in record:
            day = _to_date(record[field])
            if day:
                return day
    return None


def record_cost(record):
    for field in COST_FIELDS:
        value = record.get(field)
        if isinstance(value, (int, float)):
            return float(value)
    nested = record.get("cost") or record.get("usage")
    if isinstance(nested, dict):
        for field in COST_FIELDS:
            value = nested.get(field)
            if isinstance(value, (int, float)):
                return float(value)
    return None


def record_tier(record):
    for field in TIER_FIELDS:
        value = record.get(field)
        if isinstance(value, str):
            return value.strip().lower()
    return None


def select_tier(records):
    present = {record_tier(record) for record in records}
    for tier in TIER_PRIORITY:
        if tier in present:
            return tier
    return None


def today_total(records, today, tier):
    total = 0.0
    for record in records:
        if record_date(record) != today:
            continue
        if tier is not None and record_tier(record) != tier:
            continue
        cost = record_cost(record)
        if cost is not None:
            total += cost
    return total


def status_for(total, budget, warn_ratio):
    if budget > 0 and total >= budget:
        return "OVER"
    if budget > 0 and total >= budget * warn_ratio:
        return "WARN"
    return "OK"


def notify(message):
    print(message, flush=True)
    if not WEBHOOK_URL:
        return
    payload = json.dumps({"text": message, "content": message}).encode("utf-8")
    request = urllib.request.Request(
        WEBHOOK_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(request, timeout=10)
    except Exception as error:
        print(f"webhook delivery failed: {error}", file=sys.stderr, flush=True)


def run_once():
    records = list(read_records(LOG_PATH))
    if not records:
        print(f"no cost data at {LOG_PATH} yet", flush=True)
        return 0
    today = datetime.now().date().isoformat()
    tier = select_tier(records)
    total = today_total(records, today, tier)
    status = status_for(total, DAILY_BUDGET_USD, WARN_RATIO)
    summary = f"[{status}] {today} spend ${total:.2f} of ${DAILY_BUDGET_USD:.2f} budget"
    if status == "OK":
        print(summary, flush=True)
        return 0
    notify(summary)
    return 1 if status == "OVER" else 0


def inspect(limit=5):
    records = list(read_records(LOG_PATH))
    if not records:
        print(f"no cost data at {LOG_PATH} yet")
        return 0
    tiers = sorted({record_tier(r) for r in records if record_tier(r)})
    print(f"{len(records)} records in {LOG_PATH}")
    print(f"tiers present: {tiers}")
    print(f"selected tier: {select_tier(records)}")
    print(f"today total: ${today_total(records, datetime.now().date().isoformat(), select_tier(records)):.2f}")
    for record in records[-limit:]:
        print(json.dumps(record))
    return 0


def _interval(argv):
    for index, token in enumerate(argv):
        if token == "--interval" and index + 1 < len(argv):
            return float(argv[index + 1])
    return None


def main(argv):
    if "--inspect" in argv:
        return inspect()
    interval = _interval(argv)
    if interval is None:
        return run_once()
    while True:
        run_once()
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
