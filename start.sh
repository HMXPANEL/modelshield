#!/bin/bash
# ModelShield API — Quick Start Script
# Works on Termux and Linux/macOS
set -e

PORT=${PORT:-8000}

# Make sure .env exists
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
    echo "⚙️  Created .env from .env.example — edit it to add your API keys."
  fi
fi

echo "🚀 Starting ModelShield API on port $PORT..."
echo "   Frontend : http://localhost:$PORT/app"
echo "   Admin    : http://localhost:$PORT/admin-panel"
echo "   Docs     : http://localhost:$PORT/docs"
echo ""

python backend/main.py
