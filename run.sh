#!/usr/bin/env bash
# run.sh - Talk-to-a-Folder Run Script
# Runs backend and frontend in the current terminal

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Colors
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
GRAY='\033[0;90m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Talk-to-a-Folder - Run${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Check if setup has been run
if [ ! -d "$PROJECT_ROOT/frontend/node_modules" ]; then
    echo -e "${RED}ERROR: Frontend not set up. Run ./setup.sh first.${NC}"
    exit 1
fi

if [ ! -d "$PROJECT_ROOT/backend/venv" ]; then
    echo -e "${RED}ERROR: Backend not set up. Run ./setup.sh first.${NC}"
    exit 1
fi

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down services...${NC}"
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
    # Kill any child processes
    [ -n "$FRONTEND_PID" ] && kill -- -"$FRONTEND_PID" 2>/dev/null
    [ -n "$BACKEND_PID" ] && kill -- -"$BACKEND_PID" 2>/dev/null
    wait 2>/dev/null
    echo -e "${GREEN}All services stopped.${NC}"
}

trap cleanup EXIT INT TERM

# ---------------------------------------------------------------
# Start backend (FastAPI on port 8000)
# ---------------------------------------------------------------
echo -e "${YELLOW}Starting backend (FastAPI on port 8000)...${NC}"
(cd "$PROJECT_ROOT/backend" && "$PROJECT_ROOT/backend/venv/bin/python" -m uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!

# Give backend a moment to start
sleep 2

# ---------------------------------------------------------------
# Start frontend (Vite dev server on port 5173)
# ---------------------------------------------------------------
echo -e "${YELLOW}Starting frontend (Vite on port 5173)...${NC}"
(cd "$PROJECT_ROOT/frontend" && npm run dev) &
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  All Services Running!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${CYAN}  Frontend:    http://localhost:5173${NC}"
echo -e "${CYAN}  Backend:     http://localhost:8000${NC}"
echo -e "${CYAN}  API Docs:    http://localhost:8000/docs${NC}"
echo ""
echo -e "${GRAY}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for any process to exit
wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
