#!/usr/bin/env bash
# test.sh — Run all backend and frontend tests

set -e
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Colors
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

TOTAL_STEPS=4
BACKEND_EXIT=0
FRONTEND_EXIT=0
TSC_EXIT=0
BUILD_EXIT=0

# ── Backend tests ────────────────────────────────────────────────────
echo -e "\n${CYAN}[1/$TOTAL_STEPS] Backend tests (pytest)${NC}"
BACKEND_OUT=$(cd "$PROJECT_ROOT/backend" && "$PROJECT_ROOT/backend/venv/bin/python" -m pytest --tb=short -q 2>&1) || BACKEND_EXIT=$?
BACKEND_SUMMARY=$(echo "$BACKEND_OUT" | grep -E "passed|failed|error" | tail -1)
[ -n "$BACKEND_SUMMARY" ] && echo "  $BACKEND_SUMMARY"

# ── Frontend tests ───────────────────────────────────────────────────
echo -e "\n${CYAN}[2/$TOTAL_STEPS] Frontend tests (vitest)${NC}"
FRONTEND_OUT=$(cd "$PROJECT_ROOT/frontend" && npx vitest run 2>&1) || FRONTEND_EXIT=$?
echo "$FRONTEND_OUT" | grep -E "(Test Files|Tests |Duration)" | while read -r line; do echo "  $line"; done

# ── Frontend type check ──────────────────────────────────────────────
echo -e "\n${CYAN}[3/$TOTAL_STEPS] TypeScript type check${NC}"
TSC_OUT=$(cd "$PROJECT_ROOT/frontend" && npx tsc --noEmit 2>&1) || TSC_EXIT=$?

# ── Frontend build check ─────────────────────────────────────────────
echo -e "\n${CYAN}[4/$TOTAL_STEPS] Frontend build${NC}"
BUILD_OUT=$(cd "$PROJECT_ROOT/frontend" && npx vite build 2>&1) || BUILD_EXIT=$?
[ "$BUILD_EXIT" -eq 0 ] && echo "  Build succeeded"

# ── Summary ──────────────────────────────────────────────────────────
echo ""
[ "$BACKEND_EXIT" -ne 0 ]  && echo -e "  Backend:    ${RED}FAILED${NC}" || echo -e "  Backend:    ${GREEN}PASSED${NC}"
[ "$FRONTEND_EXIT" -ne 0 ] && echo -e "  Frontend:   ${RED}FAILED${NC}" || echo -e "  Frontend:   ${GREEN}PASSED${NC}"
[ "$TSC_EXIT" -ne 0 ]      && echo -e "  TypeScript: ${RED}FAILED${NC}" || echo -e "  TypeScript: ${GREEN}PASSED${NC}"
[ "$BUILD_EXIT" -ne 0 ]    && echo -e "  Build:      ${RED}FAILED${NC}" || echo -e "  Build:      ${GREEN}PASSED${NC}"

if [ "$BACKEND_EXIT" -ne 0 ] || [ "$FRONTEND_EXIT" -ne 0 ] || [ "$TSC_EXIT" -ne 0 ] || [ "$BUILD_EXIT" -ne 0 ]; then
    [ "$BACKEND_EXIT" -ne 0 ]  && echo -e "\n${YELLOW}--- Backend output ---${NC}\n$BACKEND_OUT"
    [ "$FRONTEND_EXIT" -ne 0 ] && echo -e "\n${YELLOW}--- Frontend output ---${NC}\n$FRONTEND_OUT"
    [ "$TSC_EXIT" -ne 0 ]      && echo -e "\n${YELLOW}--- TypeScript output ---${NC}\n$TSC_OUT"
    [ "$BUILD_EXIT" -ne 0 ]    && echo -e "\n${YELLOW}--- Build output ---${NC}\n$BUILD_OUT"
    echo ""
    echo "Tests failed"
    exit 1
fi

echo -e "\n${GREEN}All tests passed.${NC}\n"
