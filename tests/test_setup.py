"""Smoke test: proves the environment is set up and the key libraries import.

This file gets replaced by real tests in milestone 3.
"""


def test_libraries_import():
    import openpyxl
    from mcp.server.mcpserver import MCPServer  # called FastMCP in mcp v1

    import key_checkout

    assert openpyxl is not None
    assert MCPServer is not None
    assert key_checkout is not None
