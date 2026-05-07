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

Current main ships these manifest-backed feature modules: Content Review, Time Impersonator, and Voice Lobby.

### Core Commands

| Command | Description |
|---------|-------------|
| `/ping` | Health check |
| `/purge` | Delete all messages in this channel (Admin) |

### Shared Feature Commands

| Command | Description |
|---------|-------------|
| `/enable-feature` | Enable a bot feature via interactive menu (Admin) |
| `/disable-feature` | Disable a bot feature via interactive menu (Admin) |
| `/config` | Configure bot settings via interactive menu (Admin) |

### Time Impersonator Commands

| Command | Description |
|---------|-------------|
| `/t [message]` | Replace natural-language times with Discord timestamps |
| `/tz set` | Save your default timezone for timestamp conversion |

### Content Review Commands

| Command | Description |
|---------|-------------|
| `/submit` | Submit content for review |
| `/close-ticket` | Close the current review ticket |
| `/leaderboard` | View reviewer rankings |
| `/review-profile [user]` | View your or another user's review stats |

### Voice Lobby

Voice Lobby is configured through the shared feature shell. On main, it manages temporary channel lifecycle rather than exposing user-facing slash commands.

## Notes

- Prefix commands require the **Message Content Intent** enabled in the Discord Developer Portal.
- If you set `GUILD_ID`, slash commands will sync to that guild only (fast). Without it, sync is global (can take a while).

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

