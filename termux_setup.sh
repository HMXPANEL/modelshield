#!/data/data/com.termux/files/usr/bin/bash
# ─────────────────────────────────────────────────────────────
# ModelShield API — Termux Setup & Run Script
# Run once: bash termux_setup.sh
# ─────────────────────────────────────────────────────────────

set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ModelShield API — Termux Setup         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 1. Update packages
echo "📦 Updating Termux packages..."
pkg update -y && pkg upgrade -y

# 2. Install Python
echo "🐍 Installing Python..."
pkg install python python-pip -y

# 3. Install system dependencies (no Rust needed — using bcrypt 3.x)
echo "🔧 Installing system dependencies..."
pkg install libffi openssl -y

# 4. Install Python packages
echo "📥 Installing Python packages..."
pip install \
  fastapi==0.103.2 \
  uvicorn==0.24.0 \
  sqlalchemy==2.0.23 \
  "python-jose[cryptography]==3.3.0" \
  passlib==1.7.4 \
  bcrypt==3.2.2 \
  pydantic==1.10.14 \
  httpx==0.25.2 \
  python-dotenv==1.0.0 \
  python-multipart==0.0.6

# 5. Create .env if not present
if [ ! -f ".env" ]; then
  echo "⚙️  Creating .env from example..."
  cp .env.example .env
  echo ""
  echo "⚠️  IMPORTANT: Edit .env and set your API keys before starting!"
  echo "   Run: nano .env"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  To start ModelShield API:"
echo ""
echo "  Option A (recommended):"
echo "    python backend/main.py"
echo ""
echo "  Option B:"
echo "    uvicorn backend.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "  Access:"
echo "    Frontend : http://localhost:8000/app"
echo "    Admin    : http://localhost:8000/admin-panel"
echo "    API Docs : http://localhost:8000/docs"
echo "    Health   : http://localhost:8000/health"
echo ""
echo "  Default admin: admin@modelshield.dev / admin123"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
