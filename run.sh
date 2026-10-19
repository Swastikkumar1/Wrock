#!/usr/bin/env bash
set -e

echo "==========================================================="
echo "      LAUNCHING PROJECT WROCK (UNIFIED SPATIAL-AI)         "
echo "==========================================================="

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# 1. Backend
echo "[1/2] Installing backend dependencies & launching server on port 8000..."
(
  cd "$DIR"
  pip install -r backend/requirements.txt
  uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
) &
BACKEND_PID=$!

# 2. Frontend
echo "[2/2] Launching Vite HUD on port 3000..."
(
  cd "$DIR/interface/hud"
  npm install
  npm run dev
) &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" EXIT

echo ""
echo "Services active:"
echo "  -> Backend API: http://localhost:8000"
echo "  -> Frontend HUD: http://localhost:3000"
echo ""

wait
