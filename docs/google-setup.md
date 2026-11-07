# Connecting to a real Google Sheet

You only need this to point the server at a **real** tracker. With no setup at all, the server and tests use the fake sample tracker in `sample_data/`.

Setup takes about 10 minutes, and you only do it once. Google Cloud's labels change from time to time, so if a button is named slightly differently, look for the closest match.

## What you're creating, and why

| Piece | What it is | Where it lives |
|---|---|---|
| Google Cloud project | A container that holds this app's settings | Google Cloud |
| Google Sheets API (enabled) | Allows the project to use the Sheets API at all | Google Cloud |
| OAuth consent screen | The "Finance Tracker MCP wants to view your spreadsheets" page you approve | Google Cloud |
| OAuth client (Desktop app) | `credentials.json`: identifies *this app*, not you | `~/.finance-tracker-mcp/credentials.json` |
| Token | `token.json`: proof that *you* approved this app, created when you sign in | `~/.finance-tracker-mcp/token.json` |

Both files live in your home folder, **outside the repo**, so git can't see them. On Windows that's `C:\Users\<you>\.finance-tracker-mcp\`. Treat them like passwords.

## Steps

Sign in to all of these with **the Google account that owns the tracker**.

1. **Create a project.** Open https://console.cloud.google.com/. In the project picker at the top, choose **New project**, name it `finance-tracker-mcp`, and click **Create**. Make sure it's selected afterwards.

2. **Enable the Sheets API.** Go to **APIs & Services → Library**, search for **Google Sheets API**, open it, and click **Enable**.

3. **Set up the consent screen.** Go to **APIs & Services → OAuth consent screen** (this now opens **Google Auth Platform**) and click **Get started**:
   - App name: `Finance Tracker MCP`. User support email: your email.
   - Audience:
     - **Internal** if it's offered *and* the tracker belongs to that same Google Workspace account. This is the best option: no test users, no "unverified app" warning, and no 7-day sign-in expiry.
     - **External** for a personal `@gmail.com` account (Internal won't be offered there).
   - Contact email: your email. Agree to the policy, then click **Create**.

4. **External only: add yourself as a test user.** In Google Auth Platform, open **Audience → Test users → Add users**, add your own Gmail address, and click **Save**. Leave the publishing status as **Testing**. If you chose Internal, skip this step.

5. **Create the OAuth client.** Open **Clients → Create client**. Choose **Application type: Desktop app**, enter the name `finance-tracker-mcp desktop`, and click **Create**.
   **Download the JSON right away** from the dialog that appears. Google may not show the secret again later.

6. **Save the file.** Create the folder and move the download into it, renamed to `credentials.json`:
   ```powershell
   New-Item -ItemType Directory -Force "$HOME\.finance-tracker-mcp"
   Move-Item "$HOME\Downloads\client_secret_*.json" "$HOME\.finance-tracker-mcp\credentials.json"
   ```

7. **Sign in once.** From the project folder:
   ```powershell
   $env:FINANCE_SHEET_ID = "<your sheet ID or the whole sheet link>"
   .\.venv\Scripts\python.exe -m finance_tracker.check_connection
   ```
   A browser opens. Pick your account. For an External app you'll see **"Google hasn't verified this app."** That's expected for your own app in Testing mode, so click **Continue**. Approve **"See all your Google Sheets spreadsheets"** (read-only). The terminal then prints the tracker's tab names and sizes. No cell values are downloaded.

## Things to know

- **External apps only: the sign-in expires after 7 days in Testing mode.** That's Google's rule for apps that aren't published. When it happens, the server says "the sign-in expired," and you run step 7 again. To avoid this, you can set the app to **In production** under Audience. For a personal app with one user, that only means you'll keep seeing the "unverified app" screen when you sign in.
- **Read-only for now.** The app asks for `spreadsheets.readonly`. Writing (`add_transaction`) will need a separate, explicitly enabled permission.
- **To switch Google accounts,** delete `token.json` and run step 7 again.
- **To revoke access completely,** go to https://myaccount.google.com/permissions and remove "Finance Tracker MCP".
- **An alternative is a service account,** a robot Google account you share the sheet with, which avoids the browser and the 7-day limit. This project uses OAuth because it acts as *you* and doesn't need a long-lived key file.
