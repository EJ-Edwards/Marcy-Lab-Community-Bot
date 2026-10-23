DEFAULT_WELCOME_MESSAGE = (
    "Hi! How can I help you?"
)

CONFIDENTIALITY_NOTICE = (
    "Your report is confidential, not anonymous: trusted moderators can see your Discord identity."
)

DEFAULT_HELP_TEXT = (
    "**Confidential Mod-Mail**\n"
    "DM me `!modmail` to start, then send your report in this format:\n"
    "```text\n"
    "Subject: Brief topic\n"
    "Description: Explain what happened and how moderators can help.\n"
    "```\n"
    "You can also include the formatted report after `!modmail`. Attach screenshots or files if helpful.\n"
    "Send follow-up messages in this DM. Use `!modmail close` when the conversation is done.\n"
    + CONFIDENTIALITY_NOTICE
)

USER_HELP = DEFAULT_HELP_TEXT

SETUP_HELP = (
    "**Setting up Mod-Mail**\n"
    "1. Create a private control text channel. Deny `View Channel` to `@everyone` "
    "and allow trusted moderators and the bot.\n"
    "2. Give the bot permission to view and read the control channel, send messages, "
    "and save files. In the archive channel it also needs thread permissions.\n"
    "3. Set the control channel ID as `MODMAIL_CHANNEL_ID` in your hosting settings "
    "and restart the bot.\n"
    "4. In that control channel, run `!modmail setup`. Mention a private text channel "
    "when asked where case messages and history should be stored. Reply within two "
    "minutes, or say `cancel`. You can instead run "
    "`!modmail setup #private-channel @StaffRole` to configure it directly.\n"
    "Only the server owner or members with `Administrator`, `Manage Server`, "
    "`Manage Messages`, or `Moderate Members` can configure Mod-Mail.\n"
    "Case threads and message-history files go in the selected archive channel; "
    "settings are saved in a pinned text file in the control channel. Use "
    "`!modmail settings` to check configuration. Close open cases before changing "
    "to a different archive channel."
)

STAFF_HELP = (
    "**Mod-Mail staff workflow**\n"
    "Each report creates a case thread in the configured private archive channel. "
    "Reply in the case thread and the bot forwards your message to the reporter by DM.\n"
    "Use `!modmail close` in a case thread to close it and attach a `.txt` transcript. "
    "Report and reply messages are archived as `.txt` files.\n\n"
    "**Configuration (server owner/moderator)**\n"
    "`!modmail-docs` - Show setup instructions.\n"
    "`!modmail setup` - Choose where case messages and history are stored.\n"
    "`!modmail setup #private-channel [@staff-role ...]` - Set the archive directly and optionally staff roles.\n"
    "`!modmail welcome <text>` - Customize the case-opening message.\n"
    "`!modmail helptext <text>` - Customize `!modmail help`.\n"
    "`!modmail closepolicy reporters|staff` - Choose who can close a case.\n"
    "`!modmail settings` - Show current settings."
)