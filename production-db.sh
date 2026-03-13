#!/usr/bin/env bash
# production-db.sh — Smart production database manager
# Usage: ./production-db.sh
#
# What it does:
#   1. Connects to Supabase using .env.production
#   2. Detects current migration state
#   3. Applies pending migrations (or reports "already up to date")
#   4. Shows a table summary with row counts

set -e
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Colors
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
GRAY='\033[0;90m'
NC='\033[0m'

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Production Database Manager${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# -- Parse .env.production ---------------------------------------------------
ENV_FILE="$PROJECT_ROOT/.env.production"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}ERROR: .env.production not found.${NC}"
    echo -e "${GRAY}  Run ./setup.sh or copy .env.production.example to .env.production${NC}"
    exit 1
fi

DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d'=' -f2-)
if [ -z "$DATABASE_URL" ]; then
    echo -e "${RED}ERROR: DATABASE_URL not found in .env.production${NC}"
    exit 1
fi

MASKED_URL=$(echo "$DATABASE_URL" | sed 's|\(://[^:]*:\)[^@]*\(@\)|\1****\2|')
echo -e "${GRAY}  Database: $MASKED_URL${NC}"
echo ""

# -- Activate venv -----------------------------------------------------------
VENV_ACTIVATE="$PROJECT_ROOT/backend/venv/bin/activate"
if [ ! -f "$VENV_ACTIVATE" ]; then
    echo -e "${RED}ERROR: Backend venv not found. Run ./setup.sh first.${NC}"
    exit 1
fi
# shellcheck disable=SC1090
source "$VENV_ACTIVATE"

# -- Set env vars ------------------------------------------------------------
export DATABASE_URL

# -- Helper ------------------------------------------------------------------
PYTHON_EXE="$PROJECT_ROOT/backend/venv/bin/python"
REV_PATTERN='([0-9a-f]{12})'

# -- Test connection ---------------------------------------------------------
echo -e "${YELLOW}[1/3] Testing connection...${NC}"
cd "$PROJECT_ROOT/backend"

CURRENT_OUTPUT=$(alembic current 2>&1) || {
    echo -e "${RED}  ERROR: Could not connect to production database.${NC}"
    echo -e "${RED}  $(echo "$CURRENT_OUTPUT" | head -5)${NC}"
    echo ""
    echo -e "${YELLOW}  Troubleshooting:${NC}"
    echo -e "${GRAY}  - Check DATABASE_URL in .env.production${NC}"
    echo -e "${GRAY}  - Password special chars must be percent-encoded (@ -> %40, # -> %23, + -> %2B, / -> %2F)${NC}"
    echo -e "${GRAY}  - Use the Session Pooler URL from Supabase (IPv4 compatible)${NC}"
    echo -e "${GRAY}  - Direct connection requires IPv6 - will not work on most networks or Azure${NC}"
    cd "$PROJECT_ROOT"
    exit 1
}
echo -e "${GREEN}  Connected!${NC}"

# -- Detect migration state --------------------------------------------------
echo ""
echo -e "${YELLOW}[2/3] Checking migration state...${NC}"

CURRENT_REV=""
if [[ "$CURRENT_OUTPUT" =~ $REV_PATTERN ]]; then
    CURRENT_REV="${BASH_REMATCH[1]}"
    echo -e "${GRAY}  Current revision: $CURRENT_REV${NC}"
else
    echo -e "${GRAY}  No migrations applied yet (fresh database)${NC}"
fi

HEAD_OUTPUT=$(alembic heads 2>&1)
HEAD_REV=""
if [[ "$HEAD_OUTPUT" =~ $REV_PATTERN ]]; then
    HEAD_REV="${BASH_REMATCH[1]}"
    echo -e "${GRAY}  Target revision:  $HEAD_REV${NC}"
fi

# -- Apply migrations --------------------------------------------------------
echo ""
echo -e "${YELLOW}[3/3] Applying migrations...${NC}"

if [ "$CURRENT_REV" = "$HEAD_REV" ] && [ -n "$CURRENT_REV" ]; then
    echo -e "${GREEN}  Already up to date!${NC}"
else
    if [ -z "$CURRENT_REV" ]; then
        echo -e "${GRAY}  Initializing database from scratch...${NC}"
    else
        echo -e "${GRAY}  Upgrading from $CURRENT_REV to $HEAD_REV...${NC}"
    fi

    UPGRADE_OUTPUT=$(alembic upgrade head 2>&1) || {
        echo -e "${RED}  ERROR: Migration failed!${NC}"
        echo -e "${RED}  $(echo "$UPGRADE_OUTPUT" | head -10)${NC}"
        cd "$PROJECT_ROOT"
        exit 1
    }
    echo -e "${GREEN}  Migrations applied!${NC}"
fi

# -- Show table summary ------------------------------------------------------
echo ""
echo -e "${CYAN}  Table summary:${NC}"

SUMMARY_SCRIPT="$PROJECT_ROOT/backend/scripts/table_summary.py"
if [ -f "$SUMMARY_SCRIPT" ]; then
    "$PYTHON_EXE" "$SUMMARY_SCRIPT"
else
    echo -e "${GRAY}  (table_summary.py not found — skipping)${NC}"
fi

# -- Done --------------------------------------------------------------------
cd "$PROJECT_ROOT"

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}  Done!${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
