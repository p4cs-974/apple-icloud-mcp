# Testing instructions

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) installed.
- An Apple ID with two-factor authentication.
- An app-specific password from [account.apple.com](https://account.apple.com), under Sign-In and Security, then App-Specific Passwords.

## A. Automated smoke test, no Apple account needed

```bash
git clone https://github.com/p4cs-974/apple-icloud-mcp && cd apple-icloud-mcp
uv run python tests/smoke_test.py
```

Expected: the server starts over stdio with dummy credentials and exposes exactly 11 tools: `calendar_list_calendars`, `calendar_list_events`, `calendar_create_event`, `calendar_update_event`, `calendar_delete_event`, `reminders_list_lists`, `reminders_list_incomplete`, `reminders_create`, `reminders_update`, `reminders_delete` and `contacts_search`. With no credentials, a tool call returns a clear error naming `APPLE_APP_PASSWORD`. The run ends with `PASS` and never contacts iCloud.

## B. In-app test with a real account

1. Install the plugin in Grok Bot or Cursor, or point your client at the cloned repo as described in the README.
2. Set `APPLE_ID` and `APPLE_APP_PASSWORD` under Plugins, then Configure.
3. Ask the agent:
   - "List my iCloud calendars." Expect your calendar names.
   - "What is on my calendar between today and 7 days from now?" Expect events with start, end and location.
   - "List my iCloud reminder lists, then my incomplete reminders." Expect list names and open items.
   - "Search my iCloud contacts for a name I know." Expect matching contacts.
   - "Create a calendar event called Plugin test tomorrow from 10:00 to 11:00 on my Pessoal calendar." Expect a confirmation with a uid, then see it in the Calendar app.
   - "Rename that event to Plugin test 2." Expect the new title.
   - "Delete that event." Expect it to disappear from Calendar.
   - "Create a reminder called Plugin test, mark it done, then delete it." Expect each step to succeed.
4. Mail skill: ask "Help me read my iCloud mail." Expect the agent to ask which mailbox to use, such as Gmail or Outlook, and then give forwarding steps for that choice. It must not claim it can read iCloud Mail directly.
5. Error paths:
   - Unset `APPLE_APP_PASSWORD` and call any tool. The error names the missing variable.
   - Use a wrong password. The error says iCloud rejected the Apple ID or app-specific password.
6. Confirm scope: the tool list contains no mail tools, no tools that send messages, and no tools that change contacts.
7. Revoke the app-specific password at account.apple.com when you are done.

Verified by the author: the automated smoke test, plus calendar and reminders create, edit and delete, and contacts search, against a real iCloud account from inside Grok Bot. Test items were deleted afterwards.
