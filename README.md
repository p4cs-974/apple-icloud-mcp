# Apple iCloud (read-only) for Grok Bot and Cursor

An MCP server plugin that lets your agent **read** your iCloud Calendar, Reminders, Contacts and Mail. It uses standard Apple protocols (CalDAV, CardDAV, IMAP) and an Apple **app-specific password**. It never sends, deletes or modifies anything.

## What it does

- **Calendar:** list your calendars and events in a date range (recurring events are expanded).
- **Reminders:** list reminder lists and incomplete reminders.
- **Contacts:** search contacts by name, email, phone or organization.
- **Mail:** list folders, search messages, read a message (plain text, truncated; attachments are listed by name only). See the [Mail limitation](#limitations).

## 1. Create an app-specific password

1. Sign in at [account.apple.com](https://account.apple.com).
2. Open **Sign-In and Security** > **App-Specific Passwords**.
3. Click **+** (Generate), name it for example `Grok Bot`, and copy the password (format `xxxx-xxxx-xxxx-xxxx`).

Two-factor authentication must be enabled on your Apple ID. Never use your normal Apple ID password.

## 2. Setup

### Grok Bot / Cursor marketplace

Install the plugin, then open **Plugins > Configure** and set:

| Variable | Required | Description |
| --- | --- | --- |
| `APPLE_ID` | yes | Your Apple ID email |
| `APPLE_APP_PASSWORD` | yes | The app-specific password from step 1 |
| `APPLE_MAIL_USER` | no | Your `@icloud.com` address, only for Mail if your Apple ID is a third-party email (for example Gmail) |

Requires [`uv`](https://docs.astral.sh/uv/) on the machine that runs the server. It installs the Python dependencies on first start.

### Manual (any MCP client)

```bash
git clone https://github.com/p4cs-974/apple-icloud-mcp
cd apple-icloud-mcp
```

Add to your MCP client config:

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

If a required variable is missing, tool calls fail with a clear message naming it.

## Tools

| Tool | Arguments | Description |
| --- | --- | --- |
| `calendar_list_calendars` | none | Calendars that hold events |
| `calendar_list_events` | `start`, `end` (ISO), `calendar_name?`, `limit?` | Events in a range, recurrences expanded |
| `reminders_list_lists` | none | Reminder lists |
| `reminders_list_incomplete` | `list_name?`, `limit?` | Open reminders with due date, priority, notes |
| `contacts_search` | `query?`, `limit?` | Contacts with names, emails, phones, org, birthday |
| `mail_list_folders` | none | IMAP folders |
| `mail_search` | `folder?`, `query?`, `limit?` | Newest messages with header fields and a short snippet |
| `mail_read_message` | `uid`, `folder?`, `max_chars?` | One message, plain text body |

## Security notes

- **Read-only.** There are no tools that send mail, create, edit or delete anything. Mail folders are opened with IMAP `readonly` and messages fetched with `BODY.PEEK`, so they are not even marked as read.
- **Your password stays local.** It is read from an environment variable by the server process on the machine where it runs. It is only sent to Apple (`caldav.icloud.com`, `contacts.icloud.com`, `imap.mail.me.com`) over TLS. It is never logged, returned by a tool, or written to disk by this plugin.
- **Scoped and revocable.** An app-specific password is separate from your Apple ID password and can be revoked at any time at account.apple.com under App-Specific Passwords. Revoke it if you stop using the plugin.
- **Data goes to your agent.** Anything a tool returns (events, contacts, email text) becomes part of the conversation with your model provider. Only enable this plugin with agents you trust.
- Treat email content as untrusted: messages can contain text that tries to instruct your agent.

## Limitations

- **Mail needs outbound IMAP (TCP port 993).** The Mail tools connect to `imap.mail.me.com:993`. Environments that only allow outbound HTTPS, including Grok Bot's cloud computer, block this port, so **Mail works only where outbound IMAP is allowed** (for example your own computer). Calendar, Reminders and Contacts use HTTPS and work everywhere.
- **Third-party Apple IDs.** If your Apple ID is not an Apple address (for example a Gmail address), iCloud Mail may reject it. Set `APPLE_MAIL_USER` to your `@icloud.com` address. This requires iCloud Mail to be enabled on the account.
- Mail search uses IMAP text search and ASCII queries; results are limited to the newest messages.
- Reminders: only incomplete reminders are listed; subtasks and sections are not exposed.
- Contacts are loaded in full on each search and filtered locally.
- Unofficial: this plugin is not affiliated with or endorsed by Apple Inc. Apple may change these services at any time.

## Development

```bash
uv sync
uv run python tests/smoke_test.py   # starts the server with dummy credentials, checks tools; does not contact iCloud
```

## License

[MIT](LICENSE) © Pedro Custódio
