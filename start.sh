#!/bin/bash
cd "$(dirname "$0")"
source .env 2>/dev/null
export AWS_PROFILE=${AWS_PROFILE:-cloud-code}
ada credentials update --profile "$AWS_PROFILE" --account "$AWS_ACCOUNT_ID" --role "$AWS_ROLE" --once

# Kill any existing instance on port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Start server
echo "📚 Starting Book Affiliate Bot at http://localhost:8000"
uvicorn app:app --reload --port 8000 &

# Wait for server to be ready
sleep 2

# Open browser
open http://localhost:8000

# Keep script alive so Ctrl+C kills the server
wait
