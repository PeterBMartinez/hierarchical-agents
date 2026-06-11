import argparse
import json
import os
import sys
import urllib.error
import urllib.request

NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1/pages"
MAX_CHARS = 1900
MAX_BLOCKS = 95


def _rich(text: str) -> list:
    return [{"type": "text", "text": {"content": text[:MAX_CHARS]}}]


def _block(kind: str, text: str) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": _rich(text)}}


def to_blocks(content: str) -> list:
    blocks = []
    for raw in content.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            blocks.append(_block("heading_3", line[4:]))
        elif line.startswith("## "):
            blocks.append(_block("heading_2", line[3:]))
        elif line.startswith("# "):
            blocks.append(_block("heading_1", line[2:]))
        elif line.lstrip().startswith(("- ", "* ")):
            blocks.append(_block("bulleted_list_item", line.lstrip()[2:]))
        else:
            remaining = line
            while remaining:
                blocks.append(_block("paragraph", remaining[:MAX_CHARS]))
                remaining = remaining[MAX_CHARS:]
        if len(blocks) >= MAX_BLOCKS:
            blocks.append(_block("paragraph", "… (truncated)"))
            break
    return blocks


def build_payload(title, content, parent_id, parent_type, title_prop) -> dict:
    if parent_type == "database":
        parent = {"database_id": parent_id}
        properties = {title_prop: {"title": _rich(title)}}
    else:
        parent = {"page_id": parent_id}
        properties = {"title": {"title": _rich(title)}}
    return {"parent": parent, "properties": properties, "children": to_blocks(content)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Notion page from a title + text/markdown body.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--content", help="Body text; if omitted, read from stdin.")
    parser.add_argument("--file", help="Read body from this file instead of stdin.")
    parser.add_argument("--parent", default=os.environ.get("NOTION_PARENT_ID"))
    parser.add_argument("--parent-type", default=os.environ.get("NOTION_PARENT_TYPE", "page"), choices=["page", "database"])
    parser.add_argument("--title-prop", default=os.environ.get("NOTION_TITLE_PROP", "Name"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    content = args.content
    if content is None:
        content = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()

    if not args.parent:
        sys.exit("error: no parent page/database (set NOTION_PARENT_ID or pass --parent)")

    payload = build_payload(args.title, content, args.parent, args.parent_type, args.title_prop)

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return

    token = os.environ.get("NOTION_TOKEN")
    if not token:
        sys.exit("error: NOTION_TOKEN not set")

    request = urllib.request.Request(
        API,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
        print(result.get("url", "(created)"))
    except urllib.error.HTTPError as error:
        sys.exit(f"Notion API error {error.code}: {error.read().decode()[:300]}")
    except urllib.error.URLError as error:
        sys.exit(f"network error: {error}")


if __name__ == "__main__":
    main()
