# Marcy Lab Community Bot

Discord bot with NetNaval and Tic-Tac-Toe.

## Run the bot

Install dependencies with `pip install -r requirements.txt`, copy `.env.example`
to `.env`, replace the `DISCORD_TOKEN` placeholder with your bot token, then run
`python main.py`.

Enable the Message Content Intent for the bot in the Discord Developer Portal.
Keep `.env` private and never commit it or share your bot token.

## Games

The bot loads NetNaval and Tic-Tac-Toe from their respective modules in `Games/`.
