# DeDuparr v2

Duplicate media file manager for Plex Media Server. Finds and removes duplicate files using a scoring algorithm that favors efficient codecs and smaller file sizes.

## Features

- **Dual detection methods**: Plex API and SQLite direct query
- **Smart scoring**: Codec (0-55) + Container (0-40) + Resolution (0-50) + Size (0-30) = max 175 points
- **Score visualization**: Color-coded breakdown bars for each scoring category
- **Custom rules**: Add regex-based scoring adjustments
- **Radarr/Sonarr integration**: Optional notification on file deletion
- **Dark theme UI**: Built with React, TypeScript, Tailwind CSS, and shadcn/ui

## Quick Start

```bash
cp .env.example .env
# Edit .env with your paths
docker compose up -d
```

Open `http://localhost:8655` and configure your Plex connection in Settings.

## Docker Compose

```yaml
services:
  deduparr:
    image: deduparr:v2
    container_name: deduparr
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Etc/UTC
      - DATABASE_URL=sqlite:////config/deduparr.db
      - LOG_LEVEL=INFO
    volumes:
      - ./config:/config
      - /path/to/plex/config:/plex-config:ro  # Optional: for SQLite method
      - /path/to/media:/media:rw               # Same path Plex uses
    ports:
      - "8655:8655"
    restart: unless-stopped
```

## Scan Methods

### Plex API (Default)
Connects to Plex via the plexapi library. Requires Plex URL and auth token (OAuth supported).

### SQLite Direct Query
Queries a backup copy of the Plex database directly using SQL. Can find duplicates that the Plex API misses. Mount the Plex config directory read-only and set the database path in Settings.

## Scoring Algorithm

Higher score = better file = **keep**.

| Category   | Max Points | Scoring Logic                              |
|------------|------------|---------------------------------------------|
| Codec      | 55         | AV1=55, HEVC/H.265=50, H.264/AVC=30, Other=10 |
| Container  | 40         | MKV=40, MP4=20, AVI=5, Other=10             |
| Resolution | 50         | Based on pixel area (width x height)        |
| Size       | 30         | Smaller files score higher (inverted)       |

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), aiosqlite
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui
- **Database**: SQLite
- **Container**: Docker with nginx + supervisord
