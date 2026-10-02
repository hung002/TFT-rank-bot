# TFT-rank-bot

Discord bot for tracking TFT ranks and daily LP changes.

## Setup

Requires Python 3.12+.

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in both values:

- `DISCORD_TOKEN` — the bot token from the Discord developer portal
- `RIOT_API_KEY` — a Riot Games API key (https://developer.riotgames.com)

Run the bot:

```
.venv/bin/python bot.py
```

The SQLite database is created at `tft.db` next to the source files on
first start. Set `TFT_DB_PATH` to store it elsewhere.
