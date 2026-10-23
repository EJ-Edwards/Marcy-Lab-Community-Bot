# Marcy Lab Community Bot

Discord bot with NetNaval, Tic-Tac-Toe, and confidential Mod-Mail.

## Run the bot

Install dependencies with `pip install -r requirements.txt`, set the environment
variables below, then run `python main.py`.

| Variable | Purpose |
| --- | --- |
| `DISCORD_TOKEN` | Discord bot token |
| `MODMAIL_CHANNEL_ID` | ID of the private moderator-only control channel where settings are pinned; it is also the default case archive |

Enable the Message Content Intent for the bot in the Discord Developer Portal. Never
commit `.env` or share the bot token.

## Mod-Mail

1. Create a private staff text channel for Mod-Mail settings and the default case
   archive. Deny `View Channel` to `@everyone` and grant access only to trusted
   moderators and the bot.
2. Give the bot `View Channel`, `Send Messages`, `Read Message History`, `Create
   Public Threads`, `Send Messages in Threads`, `Manage Threads`, `Manage Messages`,
   `Embed Links`, and `Attach Files` in that channel.
3. Copy the channel ID (enable Developer Mode in Discord, then right-click the
   channel) and set it as `MODMAIL_CHANNEL_ID` in the hosting panel or local `.env`.
   Restart the bot.
4. A server owner or moderator with `Administrator`, `Manage Server`, `Manage
   Messages`, or `Moderate Members` permission can run `!modmail setup` in the
   private control channel. The bot asks where to store case messages and history;
   reply with a mention of a private text channel within two minutes. Reply `cancel`
   to stop without changing settings. Alternatively, run
   `!modmail setup #private-channel @Moderator @Admin` to choose the channel and
   optional staff roles directly. The bot stores configuration in a pinned `.txt`
   file in the control channel. Use `!modmail settings` to check it.
   The selected case archive must also be private and grant the bot the thread and
   file permissions listed above. Close all open cases before changing to a different
   archive channel.
   Use `!modmail-docs` in Discord to show these setup instructions.
5. Customize the member welcome/help text with `!modmail welcome <text>` and
   `!modmail helptext <text>`. Choose who can close cases with
   `!modmail closepolicy reporters` or `!modmail closepolicy staff`.
6. A member DMs the bot `!modmail` to start. The bot greets them and prompts for a
   subject and description. They reply in this format (the description can span lines):
   ```text
   Subject: Account access
   Description: Explain what happened and how moderators can help.
   ```
   They can also send the same formatted report after `!modmail`. Follow-up DMs are
   added to the open case; `!modmail close` closes it.
7. Moderators reply in the case thread in the private archive channel. The bot
   forwards moderator replies to the member's DMs. A moderator can type
   `!modmail close` in the case thread to close it and attach a `.txt` transcript.

Each case is stored as a thread and text-file records in the private Discord
channel; configuration is stored as a pinned text file, so the bot does not need a
separate database service. Keep both channels restricted to trusted moderators.
Reports are **confidential, not anonymous**:
moderators can see the reporter's name and Discord ID. Discord and the hosting
provider may also process or retain metadata. Back up the private archive if you
need protection against accidental deletion.
