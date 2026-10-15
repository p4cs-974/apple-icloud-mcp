---
name: icloud-mail-forwarding
description: Use when the user wants their agent to see their iCloud Mail (@icloud.com, @me.com or @mac.com). This plugin cannot read iCloud Mail directly. This skill asks which mailbox the agent already reads and walks the user through forwarding iCloud Mail there.
---

# iCloud Mail through forwarding

This plugin does not read iCloud Mail. Apple only exposes mail over IMAP, which many agent environments cannot reach. Instead, the user forwards iCloud Mail to a mailbox the agent can already read, such as Gmail or Outlook.

## Steps for the agent

1. Ask the user which mailbox their agent should read their iCloud mail from. Offer the mail connectors the agent actually has connected, for example Gmail or Outlook. If none is connected, say so and offer to help connect one first.
2. Do not set anything up on the user's behalf. Give them the steps below for their chosen platform and let them do it, since it needs their Apple sign-in.
3. After they finish, ask them to send a test email to their iCloud address. Then search the chosen mailbox to confirm it arrived.
4. Explain the limits: forwarding is one way, only new mail from that point on arrives, old iCloud mail and iCloud folders are not copied, and replies come from the destination account, not iCloud.

## Step 1: turn on forwarding in iCloud Mail

Menu names can differ slightly between Apple releases.

1. Sign in at icloud.com/mail.
2. Click the gear icon at the bottom of the sidebar, then Settings.
3. Open the General tab and tick "Forward my email to".
4. Enter the destination address, for example the user's Gmail address.
5. Choose whether to keep a copy in iCloud. Keeping a copy is the safer choice.
6. Click Done.

To forward only some messages, use Settings, then Rules, instead of forwarding everything.

## Step 2: make sure the destination accepts it

### Gmail
1. Check Spam after a test email. If it landed there, open it and choose "Not spam".
2. Optional: create a filter for mail sent to the iCloud address, with "Never send it to Spam" and a label such as "iCloud", so the agent can search `label:iCloud`.

### Outlook
1. Check Junk Email after a test email. If it landed there, mark it "Not junk" and add the sender to Safe senders.
2. Optional: create an inbox rule that moves mail addressed to the iCloud address into an "iCloud" folder.

### Another mailbox
Follow the same pattern: send a test email, check spam or junk, and create a filter so forwarded mail is easy to find. Only use a mailbox the agent can already read.
