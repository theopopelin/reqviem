# Reqviem

Reqviem plays audio from YouTube links directly in Discord voice channels, with slash commands and per-server playback queues.

## Features - Stack

- Play music from YouTube URLs
- Pause and resume playback
- Skip tracks
- Manage per-server queues
- Stop playback and clear the queue

- Dockerized for deployment
- Python 3.12
- discord.py

## Setup

### Requirements

- Docker and Docker Compose
- A Discord bot token

### Configuration

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token
```

Alternatively, provide the token through the DISCORD_TOKEN environment variable.

Invite your bot to your Discord server with the `bot` and `applications.commands` scopes, and grant it permission to view channels, send messages, connect to voice channels, and speak.

https://discord.com/api/oauth2/authorize?client_id="your-id"&permissions=8&scope=bot

you can use this link to invite your bot with administrator perms and replace your-id with your discord application id (not your token)

### Run

Build and start the bot:

```bash
docker compose up --build -d
```

View logs:

```bash
docker compose logs -f
```

Stop the bot:

```bash
docker compose down
```

## Commands

| Command | Description |
|---|---|
| `/play <url>` | Play or queue a YouTube link |
| `/pause` | Pause playback |
| `/resume` | Resume playback |
| `/queue` | Display the current queue |
| `/skip` | Skip the current track |
| `/stop` | Stop playback and clear the queue |

## Notes

- Queue data is stored in memory and is lost when the bot restarts.
- YouTube extraction may require updates to `yt-dlp` as YouTube changes.
- Use audio sources in compliance with applicable terms and rights.