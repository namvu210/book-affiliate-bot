#!/bin/bash
cd "$(dirname "$0")"
set -a
source ~/.env 2>/dev/null
source .env 2>/dev/null
set +a

# Kill any existing instance on port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Start server
echo "📚 Starting Book Affiliate Bot"
if [ -f localhost.pem ] && [ -f localhost-key.pem ]; then
    echo "🔒 HTTPS mode: https://localhost:8000"
    uvicorn app:app --reload --port 8000 --ssl-keyfile localhost-key.pem --ssl-certfile localhost.pem &
    sleep 2
    open https://localhost:8000
else
    echo "🌐 HTTP mode: http://localhost:8000"
    uvicorn app:app --reload --port 8000 &
    sleep 2
    open http://localhost:8000
fi

# Keep script alive so Ctrl+C kills the server
wait
