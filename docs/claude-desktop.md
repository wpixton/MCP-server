# Connecting the server to Claude Desktop (Windows)

Claude Desktop starts the server itself and talks to it over stdin/stdout. You tell it how by adding an entry to `claude_desktop_config.json`.

## 1. Find the config file

The easiest way is to open Claude Desktop, go to **Settings → Developer → Edit Config**, and it opens the right file. If you'd rather find it yourself:

| Claude Desktop install | Config file |
|---|---|
| Installer from claude.ai | `%APPDATA%\Claude\claude_desktop_config.json` |
| Microsoft Store | `%LOCALAPPDATA%\Claude-Data\claude_<id>\claude_desktop_config.json` |

For the Store version, the `%APPDATA%\Claude` folder holds only an empty `.user-data-left...` marker file. If you see that, look in `Claude-Data` instead.

**Back up the file before editing it.** It also holds your other Claude settings.

## 2. Add the server

Add an `mcpServers` section, or add to it if one exists. Keep everything else in the file as it is:

```json
{
  "mcpServers": {
    "finance-tracker": {
      "command": "C:\\path\\to\\project\\.venv\\Scripts\\python.exe",
      "args": ["-m", "finance_tracker.server"],
      "env": {
        "FINANCE_SHEET_ID": "<your Google Sheet ID>",
        "FINANCE_CREDENTIALS_DIR": "C:\\Users\\<you>\\.finance-tracker-mcp"
      }
    }
  }
}
```

- **`command`** is the virtual environment's Python, so nothing needs to be activated first.
- **Leave out `FINANCE_SHEET_ID`** to try it with the fake sample tracker instead of a real sheet.
- **`FINANCE_CREDENTIALS_DIR`** is set explicitly because Claude Desktop may start servers with only a few environment variables.
- **`add_transaction` can't write to the real sheet** unless you also add `"FINANCE_ALLOW_REAL_WRITES": "yes"` and complete the write sign-in (see [google-setup.md](google-setup.md)).

Save the file as plain UTF-8. Windows PowerShell 5.1's `Set-Content -Encoding utf8` adds a byte order mark, which can stop Claude Desktop from reading the file.

## 3. Restart and check

1. **Fully quit Claude Desktop:** right-click its tray icon and choose **Quit**. Closing the window isn't enough.
2. Reopen it. In a chat, click **+ → Connectors** and make sure **finance-tracker** is switched on.
3. Ask something like *"How did I do last month?"* and expand the tool calls to see which tools Claude chose.

## Example questions

| Ask | Tool Claude should use |
|---|---|
| "How did I do in October?" | `month_summary` (often several tools together) |
| "Am I over budget on anything?" | `budget_status` |
| "Where did my money go this month? Anything higher than normal?" | `spending_by_category` |
| "How does this month compare to last month?" | `compare_months` |
| "What were my 5 biggest expenses?" | `biggest_expenses` |
| "Show my last 5 Food purchases." | `recent_transactions` |
| "Am I caught up on tithing this year?" | `tithing_status` |
| "Add a $5 Food expense for coffee today." | `add_transaction` (refused for the real sheet unless writes are switched on) |

## Troubleshooting

Logs are in `%LOCALAPPDATA%\Claude\logs\` (`mcp.log` and `mcp-server-finance-tracker.log`).

- **"Server started and connected successfully"** followed by `initialize` means the handshake worked.
- **The server doesn't appear:** check the JSON is valid and the `command` path exists, then fully quit and reopen Claude.
- **"Not signed in to Google (or the sign-in expired)":** run `python -m finance_tracker.check_connection` with `FINANCE_SHEET_ID` set.
