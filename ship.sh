#!/bin/sh
# Usage: ./ship.sh "feat: add text watermark support"
# Stages all changes, runs tests, commits, and pushes.

set -e

MSG="${1:-update}"

echo "📋 Staging changes..."
git add -A

echo "🧪 Running tests..."
python -m pytest tests/ -q --tb=short
if [ $? -ne 0 ]; then
    echo "❌ Tests failed — fix before shipping"
    git reset HEAD
    exit 1
fi

echo "💾 Committing: $MSG"
git commit -m "$MSG"

echo "🚀 Pushing..."
git push

echo "✅ Shipped!"
