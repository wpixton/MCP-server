"""Try the MCP server from a terminal, without Claude.

It starts the server exactly the way Claude Desktop does (a separate process,
talking over stdin/stdout), calls one tool, and prints what Claude would get.

    python -m finance_tracker.demo                         -> list the tools and their descriptions
    python -m finance_tracker.demo budget_status
    python -m finance_tracker.demo budget_status month=2026-10
    python -m finance_tracker.demo recent_transactions category=Food limit=3

Uses the fake sample unless FINANCE_SHEET_ID is set in this terminal.
"""

import json
import os
import sys

import anyio
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters


def parse_arguments(pairs: list[str]) -> dict:
    """["month=2026-10", "limit=3"] -> {"month": "2026-10", "limit": 3}"""
    arguments = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        arguments[key] = int(value) if value.isdigit() else value
    return arguments


async def run(tool: str | None, arguments: dict) -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "finance_tracker.server"],
        env={k: v for k, v in os.environ.items() if k.startswith("FINANCE_")},  # pass our settings along
    )
    async with Client(server) as client:
        if tool is None:
            for t in (await client.list_tools()).tools:
                print(f"=== {t.name}\n{t.description}\n")
            return
        result = await client.call_tool(tool, arguments)
        text = result.content[0].text
        if result.is_error:
            print(f"ERROR: {text}")
        else:
            print(json.dumps(json.loads(text), indent=2))


def main() -> None:
    tool = sys.argv[1] if len(sys.argv) > 1 else None
    anyio.run(run, tool, parse_arguments(sys.argv[2:]))


if __name__ == "__main__":
    main()
