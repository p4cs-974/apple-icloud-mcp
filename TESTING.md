# Testing instructions

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) installed.
- An Apple ID with two-factor authentication.
- An app-specific password: [account.apple.com](https://account.apple.com) > Sign-In and Security > App-Specific Passwords > Generate.
- For Mail tools only: a machine that allows outbound TCP 993 (IMAP). Grok Bot's cloud computer does not.

## A. Automated smoke test (no Apple account needed)

```bash
git clone https://github.com/p4cs-974/apple-icloud-mcp && cd apple-icloud-mcp
uv run python tests/smoke_test.py
```

Expected: the server starts over stdio with dummy credentials, exposes exactly 8 tools (`calendar_list_calendars`, `calendar_list_events`, `reminders_list_lists`, `reminders_list_incomplete`, `contacts_search`, `mail_list_folders`, `mail_search`, `mail_read_message`), and with no credentials a tool call returns a clear error naming `APPLE_APP_PASSWORD`. Ends with `PASS`. This never contacts iCloud.

## B. Local test in Cursor / Grok Bot with a real account

1. Install the plugin (or point your client at the cloned repo, see README "Manual").
2. Set `APPLE_ID` and `APPLE_APP_PASSWORD` (leave `APPLE_MAIL_USER` blank unless testing Mail with a third-party Apple ID).
3. Ask the agent:
   - "List my iCloud calendars." Expect your calendar names.
   - "What is on my calendar between <today> and <today + 7 days>?" Expect events with start, end and location.
   - "List my iCloud reminder lists, then my incomplete reminders." Expect list names and open items.
   - "Search my iCloud contacts for <a name>." Expect matching contacts.
4. Mail, on a machine allowing outbound port 993:
   - "List my iCloud mail folders." Expect INBOX and other folders.
   - "Show my 5 latest emails." then "Read the first one." Expect headers, a snippet, then the body. Messages are not marked as read.
   - If login fails and your Apple ID is not an Apple address, set `APPLE_MAIL_USER` to your `@icloud.com` address.
5. Error paths:
   - Unset `APPLE_APP_PASSWORD` and call any tool: the error names the missing variable.
   - Use a wrong password: the error says iCloud rejected the Apple ID / app-specific password (401).
   - Mail where port 993 is blocked: the error explains outbound IMAP is required; Calendar, Reminders and Contacts still work.
6. Confirm read-only: the tool list contains no send, create, edit or delete tools.
7. Revoke the app-specific password at account.apple.com when done.

Verified by the author: automated smoke test (A) plus calendar, reminders and contacts against a real iCloud account from Grok Bot's cloud computer. Mail was not verified there because port 993 is blocked.
