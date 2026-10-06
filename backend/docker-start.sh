#!/bin/sh
# The image's start command: database migrations, then the API. (Kept outside /app, so it can
# say what's wrong when something is mounted over the code.)
set -e
cd /app
if [ ! -f alembic.ini ]; then
    echo "NotFlix: /app has no alembic.ini: a volume is mounted over the backend's code." >&2
    echo "On a server, don't mount ./backend:/app (that's the development setup);" >&2
    echo "use deploy/docker-compose.yml, see the README (Deploying on a server)." >&2
    exit 1
fi
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' "$@"
