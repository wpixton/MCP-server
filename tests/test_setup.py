"""Smoke test: proves the environment is set up and the key libraries import."""


def test_libraries_import():
    import googleapiclient.discovery
    import google_auth_oauthlib.flow
    import openpyxl
    from mcp.server.mcpserver import MCPServer  # called FastMCP in mcp v1

    import finance_tracker

    assert all([googleapiclient.discovery, google_auth_oauthlib.flow, openpyxl, MCPServer, finance_tracker])
