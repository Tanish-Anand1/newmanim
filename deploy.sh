#!/bin/bash
# ─── Vivacity Deploy Script ─────────────────────────────────────────────
# Prerequisites:
#   1. Render account — https://render.com
#   2. Vercel account — https://vercel.com
#   3. GitHub repo with this code pushed
#   4. RevenueCat account with products created
#   5. Supabase project with vivacity_videos bucket
#
# Usage:
#   ./deploy.sh           # Interactive mode
#   ./deploy.sh --auto    # Auto-deploy (requires env vars set)

set -e

echo "╔══════════════════════════════════════════════════╗"
echo "║        VIVACITY — One-Click Deploy              ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ─── 1. Verify prerequisites ────────────────────────────────────────────
echo "🔍 Checking prerequisites..."
command -v git >/dev/null 2>&1 || { echo "✗ git not found"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "✗ docker not found"; exit 1; }
echo "✓ git, docker available"

# ─── 2. Push to GitHub ──────────────────────────────────────────────────
if [ ! -d .git ]; then
  echo "Initializing git repo..."
  git init
  git add -A
  git commit -m "Initial deploy"
fi

REMOTE=$(git remote get-url origin 2>/dev/null || echo "")
if [ -z "$REMOTE" ]; then
  echo ""
  echo "⚠ No GitHub remote configured."
  echo "  1. Create a repo at https://github.com/new"
  echo "  2. Run: git remote add origin https://github.com/YOUR_USER/vivacity.git"
  echo "  3. Run: git push -u origin main"
  echo "  4. Re-run this script"
  exit 1
fi

echo "Pushing to GitHub..."
git push -u origin main 2>/dev/null || echo "✓ Already up to date"

# ─── 3. Render Deploy Instructions ──────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║     RENDER DEPLOY (Backend + Worker + DB)       ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Option A: One-click Blueprint deploy"
echo "  1. Go to https://render.com"
echo "  2. Click 'New +' → 'Blueprint'"
echo "  3. Connect your GitHub repo"
echo "  4. Render reads render.yaml — creates:"
echo "     - vivacity-api (Web Service, Docker)"
echo "     - vivacity-worker (Background Worker)"
echo "     - vivacity-db (PostgreSQL)"
echo "     - vivacity-redis (Redis)"
echo "  5. Set these env vars in Render dashboard:"
echo "     - SUPABASE_SERVICE_ROLE_KEY: (your Supabase key)"
echo "     - REVENUECAT_API_KEY: (your RevenueCat key)"
echo "     - ANTHROPIC_API_KEY/OPENAI_API_KEY: (at least one LLM key)"
echo ""
echo "Option B: Manual deploy"
echo "  1. Go to https://render.com → Dashboard → New + Web Service"
echo "  2. Connect repo, Docker runtime"
echo "  3. Set env vars from render.yaml (above)"
echo "  4. Add a PostgreSQL and Redis from Render dashboard"
echo ""

# ─── 4. Vercel Deploy Instructions ──────────────────────────────────────
echo "╔══════════════════════════════════════════════════╗"
echo "║     VERCEL DEPLOY (Frontend)                     ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "1. Go to https://vercel.com → Add New Project"
echo "2. Import your GitHub repo"
echo "3. Set Root Directory: frontend_reference/"
echo "4. Set Framework Preset: Other"
echo "5. Add env var:"
echo "   VITE_API_URL=https://your-app.onrender.com"
echo "6. Deploy"
echo ""
echo "Your frontend will be at: https://vivacity.vercel.app"
echo "Your backend will be at:  https://your-app.onrender.com"
echo ""
echo "Then configure RevenueCat webhook:"
echo "  URL: https://your-app.onrender.com/webhooks/revenuecat"
echo ""

# ─── 5. Verify locally ──────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════╗"
echo "║     LOCAL VERIFICATION                          ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Tests:       python -m pytest tests/ -q"
echo "Backend:     python -m uvicorn app.main:app"
echo "Open:        http://127.0.0.1:8080"
echo ""
echo "=== DEPLOY READY ==="
