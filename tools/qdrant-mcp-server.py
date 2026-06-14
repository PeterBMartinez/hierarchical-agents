#!/usr/bin/env python3
"""
Shared agent memory MCP server using the mcp library.
Hits Qdrant REST API directly — no qdrant-client dependency.
Compatible with any Qdrant version.

Environment variables:
  QDRANT_URL            e.g. http://100.84.93.86:6333
  COLLECTION_NAME       e.g. agent_memory
  EMBEDDING_MODEL       e.g. BAAI/bge-small-en-v1.5
  FASTEMBED_CACHE_PATH  e.g. /home/peter/.cache/fastembed
"""
import asyncio
import json
import os
import uuid
import urllib.request
import urllib.error

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "agent_memory")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
FASTEMBED_CACHE_PATH = os.environ.get("FASTEMBED_CACHE_PATH", "/tmp/fastembed_cache")

os.environ["FASTEMBED_CACHE_PATH"] = FASTEMBED_CACHE_PATH

VECTOR_NAME = f"fast-{EMBEDDING_MODEL.split('/')[-1].lower()}"

_embedding_model = None
_collection_ready = False


def get_model():
    global _embedding_model
    if _embedding_model is None:
        from fastembed import TextEmbedding
        _embedding_model = TextEmbedding(EMBEDDING_MODEL)
    return _embedding_model


def embed(text: str) -> list[float]:
    model = get_model()
    vectors = list(model.query_embed([text]))
    return vectors[0].tolist()


def qdrant_request(method: str, path: str, body=None) -> dict:
    url = f"{QDRANT_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"status": "error", "error": e.read().decode(), "code": e.code}


def ensure_collection():
    global _collection_ready
    if _collection_ready:
        return
    resp = qdrant_request("GET", f"/collections/{COLLECTION_NAME}")
    if resp.get("status") != "ok":
        qdrant_request("PUT", f"/collections/{COLLECTION_NAME}", {
            "vectors": {
                VECTOR_NAME: {"size": 384, "distance": "Cosine", "on_disk": True}
            }
        })
    qdrant_request("PUT", f"/collections/{COLLECTION_NAME}/index", {
        "field_name": "document",
        "field_schema": "text"
    })
    _collection_ready = True


app = Server("agent-memory")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="qdrant-store",
            description="Store a memory in shared Qdrant vector database for retrieval by any agent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "information": {
                        "type": "string",
                        "description": "Text to store as a memory"
                    },
                    "metadata": {
                        "type": "object",
                        "description": 'Extra metadata e.g. {"agent": "atlas", "type": "episodic"}',
                        "additionalProperties": True
                    }
                },
                "required": ["information"]
            }
        ),
        Tool(
            name="qdrant-find",
            description=(
                "Search shared agent memory using hybrid retrieval: semantic vector search "
                "combined with optional metadata filtering and keyword matching. "
                "Use `filter` to narrow by agent or type. "
                "Use `must_text` when searching for exact terms that semantic search may miss: "
                "model names (claude-opus-4-8), version numbers (v1.7.4), specific metrics "
                "(57%), project names (Warp 9), or any proper noun where exact match matters. "
                "`filter` and `must_text` are ANDed together."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Semantic search query"
                    },
                    "filter": {
                        "type": "object",
                        "description": (
                            "Metadata key-value pairs to filter results. "
                            "e.g. {\"agent\": \"atlas\"} or {\"type\": \"episodic\"}. "
                            "Multiple keys are ANDed together."
                        ),
                        "additionalProperties": True
                    },
                    "must_text": {
                        "type": "string",
                        "description": (
                            "Keyword that MUST appear verbatim in the stored content. "
                            "Use for exact terms: model names, version numbers, "
                            "specific metric values, project names, contact names. "
                            "ANDed with `filter`."
                        )
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    loop = asyncio.get_event_loop()

    if name == "qdrant-store":
        information = arguments["information"]
        metadata = arguments.get("metadata")

        ensure_collection()
        vector = await loop.run_in_executor(None, embed, information)
        point_id = uuid.uuid4().hex

        qdrant_request("PUT", f"/collections/{COLLECTION_NAME}/points", {
            "points": [{
                "id": point_id,
                "vector": {VECTOR_NAME: vector},
                "payload": {"document": information, "metadata": metadata}
            }]
        })
        return [TextContent(type="text", text=f"Stored in {COLLECTION_NAME}: {information[:80]}")]

    elif name == "qdrant-find":
        query = arguments["query"]
        limit = arguments.get("limit", 5)
        meta_filter = arguments.get("filter")
        must_text = arguments.get("must_text")

        ensure_collection()
        vector = await loop.run_in_executor(None, embed, query)

        body: dict = {
            "vector": {"name": VECTOR_NAME, "vector": vector},
            "limit": limit,
            "with_payload": True,
        }
        conditions = []
        if meta_filter:
            conditions.extend(
                {"key": f"metadata.{k}", "match": {"value": v}}
                for k, v in meta_filter.items()
            )
        if must_text:
            conditions.append({"key": "document", "match": {"text": must_text}})
        if conditions:
            body["filter"] = {"must": conditions}

        resp = qdrant_request("POST", f"/collections/{COLLECTION_NAME}/points/search", body)

        points = resp.get("result", [])
        if not points:
            return [TextContent(type="text", text=f"No memories found for: {query}")]

        lines = [f"Results for '{query}':"]
        for p in points:
            payload = p.get("payload", {})
            doc = payload.get("document", "")
            meta = payload.get("metadata", {})
            lines.append(
                f"<entry><content>{doc}</content>"
                f"<metadata>{json.dumps(meta)}</metadata></entry>"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()
