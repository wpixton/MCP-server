"""Tests for server.py, through a real MCP client.

Most tests connect the client to the server in memory (fast). The last one
starts `python -m finance_tracker.server` as a separate process and talks to it
over stdin/stdout -- exactly how Claude Desktop runs it.
"""

import json
import sys
from datetime import date, datetime

import anyio
import pytest
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters

from finance_tracker import config, server
from finance_tracker.sample_tracker import build_sample_tracker

TOOLS = {"month_summary", "budget_status", "spending_by_category", "compare_months",
         "biggest_expenses", "recent_transactions", "tithing_status"}


@pytest.fixture(scope="module")
def sample_path(tmp_path_factory):
    return build_sample_tracker(tmp_path_factory.mktemp("sample") / "tracker.xlsx", now=datetime(2026, 11, 20, 14, 0))


@pytest.fixture(autouse=True)
def use_sample(monkeypatch, sample_path):
    """Every test reads the fake sample, and "today" is pinned to 20 Nov 2026."""
    monkeypatch.setenv(config.SAMPLE_PATH_VAR, str(sample_path))
    monkeypatch.setattr(server, "today", lambda: date(2026, 11, 20))


def connect_and(action):
    """Connect an MCP client to the server in memory, run `action(client)`, return its result."""
    async def run():
        async with Client(server.server) as client:
            return await action(client)
    return anyio.run(run)


def call(name: str, **arguments):
    return connect_and(lambda client: client.call_tool(name, arguments))


def data(result) -> dict:
    assert not result.is_error, result.content
    return json.loads(result.content[0].text)


def error_text(result) -> str:
    assert result.is_error
    return result.content[0].text


# --- What Claude sees -------------------------------------------------------

def test_all_tools_are_listed_and_marked_read_only():
    tools = connect_and(lambda client: client.list_tools()).tools
    assert {t.name for t in tools} == TOOLS
    assert all(t.annotations.read_only_hint for t in tools)


def test_every_tool_says_when_to_use_it():
    for tool in connect_and(lambda client: client.list_tools()).tools:
        assert "Use for" in tool.description, tool.name


def test_parameter_descriptions_reach_the_schema():
    tools = {t.name: t for t in connect_and(lambda client: client.list_tools()).tools}
    month = tools["budget_status"].input_schema["properties"]["month"]
    assert "YYYY-MM" in month["description"]


def test_server_instructions_reach_the_client():
    async def read_instructions(client):
        return client.instructions  # sent once when the client connects

    text = connect_and(read_instructions)
    assert "Transfer" in text and "YYYY-MM" in text


# --- Calling the tools ---------------------------------------------------------

@pytest.mark.parametrize("name, arguments", [
    ("month_summary", {}),
    ("budget_status", {"month": "2026-10"}),
    ("spending_by_category", {}),
    ("compare_months", {"month": "2026-11", "compare_to": "2026-09"}),
    ("biggest_expenses", {"limit": 3}),
    ("recent_transactions", {"kind": "expense", "category": "Food"}),
    ("tithing_status", {"year": 2026}),
])
def test_every_tool_runs(name, arguments):
    assert data(call(name, **arguments))


def test_no_month_means_this_month():
    assert data(call("budget_status"))["month"] == "2026-11"
    compared = data(call("compare_months"))
    assert (compared["month"], compared["compare_to"]) == ("2026-11", "2026-10")


def test_budget_status_finds_the_overspending():
    assert "Shopping" in data(call("budget_status"))["over_budget"]


def test_category_names_ignore_case():
    result = data(call("recent_transactions", category="food"))
    assert result["filters"]["category"] == "Food"


# --- Clear errors instead of crashes --------------------------------------------

def test_bad_month_is_explained():
    assert "2026-11" in error_text(call("month_summary", month="November"))


def test_unknown_category_lists_the_valid_ones():
    message = error_text(call("recent_transactions", category="Groceries"))
    assert "Unknown category" in message and "Food" in message


def test_limit_out_of_range_is_rejected():
    assert call("biggest_expenses", limit=500).is_error


def test_missing_sample_explains_how_to_make_it(monkeypatch, tmp_path):
    monkeypatch.setenv(config.SAMPLE_PATH_VAR, str(tmp_path / "missing.xlsx"))
    assert "sample_tracker" in error_text(call("month_summary"))


# --- The real thing: a separate process over stdio --------------------------------

def test_server_works_over_stdio_like_claude_desktop(sample_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "finance_tracker.server"],
        env={config.SAMPLE_PATH_VAR: str(sample_path)},  # fake sample only; no FINANCE_SHEET_ID
    )

    async def run():
        async with Client(params) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool("budget_status", {"month": "2026-11"})
            return {t.name for t in tools}, result

    names, result = anyio.run(run)
    assert names == TOOLS
    assert "Shopping" in data(result)["over_budget"]
