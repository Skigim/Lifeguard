# Lifeguard

Discord bot (rewrite). Python 3.11+, `discord.py`.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
notepad .env.test   # add DISCORD_TOKEN= followed by your test bot token, then save
.\.venv\Scripts\python -m lifeguard
```

`BOT_ENV` defaults to `test` and loads `.env.test`. Production requires explicitly
setting `BOT_ENV=production` (loads `.env.production`).

## Develop

```powershell
.\.venv\Scripts\ruff check src tests
.\.venv\Scripts\pytest
```

## Docker

```powershell
docker build -t lifeguard .
docker run --env-file .env.test -p 8080:8080 -v lifeguard-data:/data lifeguard
```

## Features

- [GitHub bridge](docs/features/github.md) — mirror GitHub issues and pull requests into Discord forums.
- [Greeter](docs/features/greeter.md) — enable the `/greet` command.
