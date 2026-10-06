#!/bin/sh
# The image's start command: database migrations, then the API (arguments go to uvicorn, e.g.
# --reload). Kept outside /app, so it can say what's wrong when something is mounted over the
# code.
set -e
echo "NotFlix backend ${NOTFLIX_VERSION:-dev}"
cd /app
if [ ! -d app ] || [ ! -d alembic ]; then
    echo "NotFlix: /app doesn't have the backend's code: a volume is mounted over it." >&2
    echo "The repository's docker-compose.yml mounts ./backend:/app for development; on a" >&2
    echo "server use deploy/docker-compose.yml (see the README, Deploying on a server)." >&2
    exit 1
fi
python -m app.migrate
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' "$@"
