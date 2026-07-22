"""rss-mcp — MCP server for RSS and Atom feeds.

Fetches, parses, and filters RSS 1.0/2.0 and Atom feeds using the standard
`feedparser` library. Works with any public feed URL. Nothing leaves your
machine except the HTTPS GET to the feed URL.

Tools: fetch_feed, search_entries, list_feed_metadata.

Author: Bartosz Kuć <firma@bartosza.pl>
Repo:   https://github.com/bartosz-kuc/rss-mcp
License: MIT
"""

import asyncio
import json
from typing import Any

import feedparser

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

USER_AGENT = "rss-mcp/1.0 (+https://github.com/bartosz-kuc/rss-mcp)"


def _entry_to_dict(e: Any) -> dict:
    return {
        "title": getattr(e, "title", None),
        "link": getattr(e, "link", None),
        "published": getattr(e, "published", None) or getattr(e, "updated", None),
        "author": getattr(e, "author", None),
        "summary": getattr(e, "summary", None),
        "id": getattr(e, "id", None) or getattr(e, "link", None),
        "tags": [t.term for t in getattr(e, "tags", [])] if hasattr(e, "tags") else [],
    }


def _feed_info(f: feedparser.FeedParserDict, url: str, entry_count: int | None) -> dict:
    channel = f.feed
    info = {
        "url": url,
        "title": getattr(channel, "title", None),
        "subtitle": getattr(channel, "subtitle", None),
        "link": getattr(channel, "link", None),
        "language": getattr(channel, "language", None),
        "updated": getattr(channel, "updated", None),
        "generator": getattr(channel, "generator", None),
    }
    if entry_count is not None:
        info["total_entries"] = len(f.entries)
        info["returned"] = entry_count
    if f.bozo:
        info["parser_warning"] = str(f.bozo_exception)[:200] if f.bozo_exception else "feed is not fully well-formed"
    return info


def _parse(url: str) -> feedparser.FeedParserDict:
    return feedparser.parse(url, agent=USER_AGENT)


server = Server("rss")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="fetch_feed",
            description=(
                "Fetch and parse an RSS or Atom feed. Returns feed metadata (title, subtitle, language) and a list "
                "of entries (title, link, published date, author, summary, tags). Use `limit` to cap how many "
                "entries you get back — feeds can be huge. Works with any publicly-accessible feed URL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Feed URL (RSS 1.0, RSS 2.0, or Atom)"},
                    "limit": {"type": "integer", "default": 20, "description": "Maximum number of entries to return (default 20)"},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="search_entries",
            description=(
                "Fetch a feed and return only entries whose title or summary contain a keyword (case-insensitive). "
                "Useful when you want the AI to check a feed for specific topics without wading through everything."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Feed URL"},
                    "query": {"type": "string", "description": "Keyword to match against title or summary (case-insensitive substring)"},
                    "limit": {"type": "integer", "default": 20, "description": "Maximum matches to return"},
                },
                "required": ["url", "query"],
            },
        ),
        Tool(
            name="list_feed_metadata",
            description=(
                "Fetch metadata for one or more feeds without loading all entries — title, subtitle, entry count, "
                "last update time. Useful for building a dashboard of feeds you follow."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}, "description": "List of feed URLs"},
                },
                "required": ["urls"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "fetch_feed":
        url = arguments["url"]
        limit = int(arguments.get("limit", 20))
        f = _parse(url)
        entries = [_entry_to_dict(e) for e in f.entries[:limit]]
        result = {"feed": _feed_info(f, url, len(entries)), "entries": entries}
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    if name == "search_entries":
        url = arguments["url"]
        query = arguments["query"].lower().strip()
        if not query:
            raise ValueError("query must be non-empty")
        limit = int(arguments.get("limit", 20))
        f = _parse(url)
        matches: list[dict] = []
        for e in f.entries:
            title = (getattr(e, "title", "") or "").lower()
            summary = (getattr(e, "summary", "") or "").lower()
            if query in title or query in summary:
                matches.append(_entry_to_dict(e))
                if len(matches) >= limit:
                    break
        result = {"feed": _feed_info(f, url, len(matches)), "query": arguments["query"], "matches": matches}
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    if name == "list_feed_metadata":
        urls = arguments["urls"]
        if not isinstance(urls, list) or not urls:
            raise ValueError("urls must be a non-empty list")
        feeds = []
        for url in urls:
            try:
                f = _parse(url)
                info = _feed_info(f, url, None)
                info["total_entries"] = len(f.entries)
                feeds.append(info)
            except Exception as exc:
                feeds.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
        return [TextContent(type="text", text=json.dumps({"feeds": feeds}, ensure_ascii=False, indent=2))]

    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
