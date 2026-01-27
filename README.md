# Lifeguard (Discord Bot)

Minimal development scaffold for a custom Discord bot called **Lifeguard**.

## Prereqs

- Python 3.11+ (3.12 is fine)
- A Discord application + bot token

## Setup (Windows / PowerShell)

1) Create a virtual environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) Install dependencies

```powershell
python -m pip install -U pip
pip install -r requirements.txt
pip install -e .
```

3) Configure environment

- Copy `.env.example` to `.env`
- Set `DISCORD_TOKEN`
- Optional: set `GUILD_ID` to speed up slash-command sync during development

4) Run

```powershell
python -m lifeguard
```

## Commands

### Core Commands

| Command | Description |
|---------|-------------|
| `/ping` | Health check |
| `/purge` | Delete all messages in this channel (Admin) |

### Albion Commands

| Command | Description |
|---------|-------------|
| `/albion-price <item>` | Search item prices on the Albion market |
| `/build <id>` | Fetch a saved build by ID |

### Content Review Commands

| Command | Description |
|---------|-------------|
| `/enable-feature` | Enable a bot feature via interactive menu (Admin) |
| `/config` | Configure bot settings via interactive menu (Admin) |
| `/submit` | Submit content for review |
| `/close-ticket` | Close the current review ticket |
| `/leaderboard` | View reviewer rankings |
| `/review-profile [user]` | View your or another user's review stats |

## Notes

- Prefix commands require the **Message Content Intent** enabled in the Discord Developer Portal.
- If you set `GUILD_ID`, slash commands will sync to that guild only (fast). Without it, sync is global (can take a while).

## Albion APIs (West)

- Market data (default): `https://west.albion-online-data.com`
- Game Info (kills/battles): `https://gameinfo.albiononline.com/api/gameinfo`

## Backend

Lifeguard is set up to use Firebase Admin SDK + Firestore.

- Configure via `FIREBASE_ENABLED`, `FIREBASE_CREDENTIALS_PATH`, and (optionally) `FIREBASE_PROJECT_ID` (see `.env.example`).

## Configuration

All bot configuration is done through Discord slash commands with interactive menus. No external dashboard required.

### Content Review Setup

1. Use `/enable-feature` → Select "Content Review" → Choose ticket category and reviewer role
2. Use `/config` → Select actions from the dropdown to customize fields, categories, and settings

Notes:
- Do not commit your service account JSON.
- You can keep `FIREBASE_ENABLED=false` during early bot-only development.

