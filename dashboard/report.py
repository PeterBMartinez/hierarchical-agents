import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents_app.activity import report


def main() -> None:
    parser = argparse.ArgumentParser(description="Report an agent status to the dashboard.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--task", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--kind", default="hermit")
    parser.add_argument("--role", default="")
    args = parser.parse_args()
    report(
        args.name,
        args.status,
        task=args.task,
        model=args.model,
        kind=args.kind,
        role=args.role or None,
    )


if __name__ == "__main__":
    main()
