import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import append_message, get_or_create_conv, read_thread


def unanswered(agent: str, conv_id: str = None) -> list:
    messages = read_thread(agent, conv_id=conv_id)
    last_agent_index = -1
    for index, message in enumerate(messages):
        if message.get("from") == "agent":
            last_agent_index = index
    return [m for m in messages[last_agent_index + 1:] if m.get("from") == "user"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard chat + inter-agent task bridge.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    inbox = sub.add_parser("inbox", help="Print unanswered incoming messages for this agent.")
    inbox.add_argument("--name", required=True)
    inbox.add_argument("--conv-id", default=None)

    reply = sub.add_parser("reply", help="Post a reply from this agent.")
    reply.add_argument("--name", required=True)
    reply.add_argument("--text", required=True)
    reply.add_argument("--conv-id", default=None)

    send = sub.add_parser("send", help="Send a task to another agent's inbox (delegation).")
    send.add_argument("--to", required=True)
    send.add_argument("--text", required=True)
    send.add_argument("--from", dest="frm", default="", help="Delegating agent; its thread receives the worker's reply.")

    thread = sub.add_parser("thread", help="Dump another agent's full conversation thread.")
    thread.add_argument("--name", required=True)
    thread.add_argument("--conv-id", default=None)

    args = parser.parse_args()

    if args.cmd == "inbox":
        pending = unanswered(args.name, conv_id=args.conv_id)
        if not pending:
            print("(no new messages)")
            return
        for message in pending:
            print(f"[{message.get('ts','')}] {message.get('text','')}")
        return

    if args.cmd == "reply":
        conv_id = args.conv_id
        delegators = []
        for m in unanswered(args.name, conv_id=conv_id):
            d = m.get("delegator")
            if d and d not in delegators:
                delegators.append(d)
        append_message(args.name, "agent", args.text, conv_id=conv_id)
        for d in delegators:
            append_message(d, "agent", f"↩ from {args.name}: {args.text}", {"via": args.name})
        note = f"; forwarded to {', '.join(delegators)}" if delegators else ""
        print("reply posted" + note)
        return

    if args.cmd == "send":
        extra = {"delegator": args.frm} if args.frm else None
        append_message(args.to, "user", args.text, extra)
        print(f"task sent to {args.to}")
        return

    for message in read_thread(args.name, conv_id=args.conv_id):
        print(f"{message.get('from','?').upper()}: {message.get('text','')}")


if __name__ == "__main__":
    main()
