# Apple iCloud Calendar, Reminders and Contacts for Grok Bot and Cursor

An MCP server plugin that lets your agent read your iCloud Calendar, Reminders and Contacts, and create, edit and delete calendar events and reminders. It uses standard Apple protocols, CalDAV and CardDAV, and an Apple app-specific password. Contacts are read-only, and the plugin has no mail tools and sends no messages.

iCloud Mail is not supported directly. The plugin includes a skill that helps you forward iCloud Mail to a mailbox your agent already reads. See [iCloud Mail](#icloud-mail).

## What it does

- **Calendar:** list your calendars and the events in a date range, with recurring events expanded. Create, edit and delete events.
- **Reminders:** list reminder lists and incomplete reminders. Create, edit, complete and delete reminders.
- **Contacts:** search contacts by name, email, phone or organization.
- **Skill `icloud-mail-forwarding`:** asks which mailbox your agent should read your iCloud mail from, such as Gmail or Outlook, and walks you through setting up forwarding.

## 1. Create an app-specific password

1. Sign in at [account.apple.com](https://account.apple.com).
2. Open Sign-In and Security, then App-Specific Passwords.
3. Click the plus button, name it for example `Grok Bot`, and copy the password. It looks like `xxxx-xxxx-xxxx-xxxx`.

Two-factor authentication must be enabled on your Apple ID. Never use your normal Apple ID password.

## 2. Setup

### Grok Bot and Cursor marketplace

Install the plugin, then open Plugins, then Configure, and set:

| Variable | Required | Description |
| --- | --- | --- |
| `APPLE_ID` | yes | Your Apple ID email |
| `APPLE_APP_PASSWORD` | yes | The app-specific password from step 1 |

The machine that runs the server needs [`uv`](https://docs.astral.sh/uv/). It installs the Python dependencies on first start.

### Manual setup with any MCP client

```bash
git clone https://github.com/p4cs-974/apple-icloud-mcp
cd apple-icloud-mcp
```

Add this to your MCP client config:

```json
{
  "mcpServers": {
    "apple-icloud": {
      "command": "uv",
      "args": ["run", "--quiet", "--directory", "/path/to/apple-icloud-mcp", "python", "server.py"],
      "env": {
        "APPLE_ID": "you@example.com",
        "APPLE_APP_PASSWORD": "xxxx-xxxx-xxxx-xxxx"
      }
    }
  }
}
```

If a required variable is missing, tool calls fail with a message that names it.

## Tools

| Tool | Arguments | Description |
| --- | --- | --- |
| `calendar_list_calendars` | none | Calendars that hold events |
| `calendar_list_events` | `start`, `end` as ISO dates, `calendar_name?`, `limit?` | Events in a range with uid, recurrences expanded |
| `reminders_list_lists` | none | Reminder lists |
| `reminders_list_incomplete` | `list_name?`, `limit?` | Open reminders with uid, due date, priority and notes |
| `calendar_create_event` | `title`, `start`, `end?`, `calendar_name?`, `location?`, `description?`, `timezone_name?`, `alarm_minutes_before?` | Creates an event and returns its uid. A plain date makes an all-day event |
| `calendar_update_event` | `uid`, and any field to change | Changes an existing event |
| `calendar_delete_event` | `uid`, `calendar_name?` | Permanently deletes an event |
| `reminders_create` | `title`, `list_name?`, `due?`, `notes?`, `priority?`, `timezone_name?` | Creates a reminder and returns its uid |
| `reminders_update` | `uid`, and any field to change, `completed?` | Changes or completes a reminder |
| `reminders_delete` | `uid`, `list_name?` | Permanently deletes a reminder |
| `contacts_search` | `query?`, `limit?` | Contacts with names, emails, phones, organization and birthday |

## iCloud Mail

This plugin cannot read iCloud Mail. Apple only offers mail over IMAP, and many agent environments only allow outbound HTTPS, so a direct mail connection would fail for many users.

Instead, use the bundled `icloud-mail-forwarding` skill. Ask your agent to help you read your iCloud mail. It will ask which mailbox it should use, for example Gmail or Outlook, and give you the steps to forward iCloud Mail there. The agent then reads the forwarded mail through its existing connection to that mailbox.

What to expect from forwarding:

- Only new mail arrives after you turn it on. Old messages and iCloud folders are not copied.
- Replies come from the destination account, not from iCloud.
- You set it up yourself in iCloud Mail, so the plugin never needs your mail credentials.

## Security notes

- **Writes are limited to your calendar events and reminders.** The write tools only touch items you ask the agent to change. Delete tools remove items permanently, so review what your agent plans to delete. Contacts cannot be changed. There are no tools that send email or messages.
- **Your password stays local.** It is read from an environment variable by the server process on the machine where it runs. It is only sent to Apple at `caldav.icloud.com` and `contacts.icloud.com` over TLS. It is never logged, returned by a tool or written to disk by this plugin.
- **Scoped and revocable.** An app-specific password is separate from your Apple ID password. You can revoke it at any time at account.apple.com under App-Specific Passwords. Revoke it if you stop using the plugin.
- **Data goes to your agent.** Anything a tool returns, such as events and contacts, becomes part of the conversation with your model provider. Only enable this plugin with agents you trust.
- **Untrusted text.** Event titles, notes and contact fields can contain text written by other people. Treat them as data, not instructions.

## Limitations

- Mail is not supported directly. See [iCloud Mail](#icloud-mail).
- Reminders: only incomplete reminders are listed. Subtasks and sections are not exposed.
- Editing a recurring event changes the whole series. Single occurrences cannot be edited separately.
- Events created without a time zone name and without an offset are floating times, which iCloud shows in each device's own time zone. Pass `timezone_name`, for example `America/Sao_Paulo`, to fix the zone.
- Contacts are loaded in full on each search and filtered locally.
- This plugin is unofficial. It is not affiliated with or endorsed by Apple Inc. Apple may change these services at any time.

## Development

```bash
uv sync
uv run python tests/smoke_test.py   # starts the server with dummy credentials and checks the tools, without contacting iCloud
```

## License

[MIT](LICENSE) © Pedro Custódio
