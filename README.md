# Lifeguard

Discord bot (rewrite). Python 3.11+, `discord.py`.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
Copy-Item .env.example .env.test   # then fill in DISCORD_TOKEN (use a TEST bot)
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
docker run --env-file .env.test lifeguard
```
