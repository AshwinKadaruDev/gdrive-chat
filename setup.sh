#!/usr/bin/env bash
# setup.sh - Talk-to-a-Folder Setup Script
# One-time setup for local development

set -e
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Colors
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
GRAY='\033[0;90m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Talk-to-a-Folder - Setup${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ---------------------------------------------------------------
# 1. Check prerequisites
# ---------------------------------------------------------------
echo -e "${YELLOW}[1/7] Checking prerequisites...${NC}"

# Check Python
if command -v python3 &>/dev/null; then
    PYTHON_CMD=python3
elif command -v python &>/dev/null; then
    PYTHON_CMD=python
else
    echo -e "${RED}  ERROR: Python not found. Please install Python 3.12+ from https://python.org${NC}"
    exit 1
fi
echo -e "${GREEN}  Python: $($PYTHON_CMD --version)${NC}"

# Check Node.js
if ! command -v node &>/dev/null; then
    echo -e "${RED}  ERROR: Node.js not found. Please install Node.js 20+ from https://nodejs.org${NC}"
    exit 1
fi
echo -e "${GREEN}  Node.js: $(node --version)${NC}"

# Check npm
if ! command -v npm &>/dev/null; then
    echo -e "${RED}  ERROR: npm not found.${NC}"
    exit 1
fi
echo -e "${GREEN}  npm: v$(npm --version)${NC}"

# Check for uv (optional, fall back to pip)
USE_UV=false
if command -v uv &>/dev/null; then
    echo -e "${GREEN}  uv: $(uv --version) (will use for faster installs)${NC}"
    USE_UV=true
else
    echo -e "${GRAY}  uv: not found (using pip instead)${NC}"
fi

echo ""

# ---------------------------------------------------------------
# 2. Create Python virtual environment
# ---------------------------------------------------------------
VENV_PATH="$PROJECT_ROOT/backend/venv"
PIP_EXE="$VENV_PATH/bin/pip"
PYTHON_EXE="$VENV_PATH/bin/python"

if [ ! -d "$VENV_PATH" ]; then
    echo -e "${YELLOW}[2/7] Creating Python virtual environment...${NC}"
    $PYTHON_CMD -m venv "$VENV_PATH"
    echo -e "${GREEN}  Virtual environment created at backend/venv${NC}"
else
    echo -e "${GREEN}[2/7] Virtual environment already exists.${NC}"
fi

# ---------------------------------------------------------------
# 3. Install backend Python dependencies
# ---------------------------------------------------------------
echo -e "${YELLOW}[3/7] Installing backend dependencies...${NC}"
if [ "$USE_UV" = true ]; then
    uv pip install --python "$PYTHON_EXE" -r "$PROJECT_ROOT/backend/requirements.txt" --quiet
else
    "$PIP_EXE" install -r "$PROJECT_ROOT/backend/requirements.txt" --quiet
fi
echo -e "${GREEN}  Backend dependencies installed.${NC}"

# ---------------------------------------------------------------
# 4. Install frontend dependencies
# ---------------------------------------------------------------
echo -e "${YELLOW}[4/7] Installing frontend dependencies...${NC}"

if [ -d "$PROJECT_ROOT/frontend/node_modules" ]; then
    echo -e "${GRAY}  node_modules exists, checking for updates...${NC}"
fi

(cd "$PROJECT_ROOT/frontend" && npm install --no-audit --no-fund) >/dev/null 2>&1
echo -e "${GREEN}  Frontend dependencies installed.${NC}"

# ---------------------------------------------------------------
# 5. Create .env from .env.example if it doesn't exist
# ---------------------------------------------------------------
echo -e "${YELLOW}[5/7] Checking .env file...${NC}"
ENV_FILE="$PROJECT_ROOT/.env"
ENV_EXAMPLE="$PROJECT_ROOT/.env.example"
ENV_CREATED=false

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo -e "${GREEN}  .env created from .env.example${NC}"
        ENV_CREATED=true
    else
        echo -e "${RED}  WARNING: .env.example not found. Create .env manually.${NC}"
    fi
else
    echo -e "${GREEN}  .env already exists.${NC}"
fi

# ---------------------------------------------------------------
# 6. Create .env.production from template if it doesn't exist
# ---------------------------------------------------------------
echo -e "${YELLOW}[6/7] Checking .env.production file...${NC}"
ENV_PROD_FILE="$PROJECT_ROOT/.env.production"
ENV_PROD_EXAMPLE="$PROJECT_ROOT/.env.production.example"
ENV_PROD_CREATED=false

if [ ! -f "$ENV_PROD_FILE" ]; then
    if [ -f "$ENV_PROD_EXAMPLE" ]; then
        cp "$ENV_PROD_EXAMPLE" "$ENV_PROD_FILE"
        echo -e "${GREEN}  .env.production created from .env.production.example${NC}"
        ENV_PROD_CREATED=true
    else
        echo -e "${YELLOW}  WARNING: .env.production.example not found.${NC}"
    fi
else
    echo -e "${GREEN}  .env.production already exists.${NC}"
fi

# ---------------------------------------------------------------
# 7. Generate secrets if not already in .env
# ---------------------------------------------------------------
echo -e "${YELLOW}[7/7] Checking security keys...${NC}"

if [ -f "$ENV_FILE" ]; then
    ENV_CONTENT="$(cat "$ENV_FILE")"

    # Generate ENCRYPTION_KEY (Fernet key) if placeholder or missing
    if echo "$ENV_CONTENT" | grep -q "ENCRYPTION_KEY=your-fernet-key" || ! echo "$ENV_CONTENT" | grep -q "ENCRYPTION_KEY=.\+"; then
        echo -e "${YELLOW}  Generating ENCRYPTION_KEY (Fernet)...${NC}"
        FERNET_KEY=$("$PYTHON_EXE" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || true)
        if [ -n "$FERNET_KEY" ]; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$FERNET_KEY|" "$ENV_FILE"
            else
                sed -i "s|ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$FERNET_KEY|" "$ENV_FILE"
            fi
            echo -e "${GREEN}  ENCRYPTION_KEY generated.${NC}"
        else
            echo -e "${YELLOW}  WARNING: Could not generate Fernet key (cryptography not installed yet).${NC}"
        fi
    fi
fi

# ---------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------
echo -e "${YELLOW}[6/7] Setting up database...${NC}"

# Try to create the PostgreSQL database (requires psql on PATH)
if command -v psql &>/dev/null; then
    if ! psql -U postgres -lqt 2>/dev/null | grep -q "talk_to_folder"; then
        echo -e "${YELLOW}  Creating database 'talk_to_folder'...${NC}"
        if psql -U postgres -c "CREATE DATABASE talk_to_folder;" 2>/dev/null; then
            echo -e "${GREEN}  Database created.${NC}"
        else
            echo -e "${YELLOW}  WARNING: Could not create database. Create 'talk_to_folder' manually.${NC}"
        fi
    else
        echo -e "${GREEN}  Database 'talk_to_folder' already exists.${NC}"
    fi
else
    echo -e "${YELLOW}  WARNING: psql not found. Create the 'talk_to_folder' database manually.${NC}"
fi

# Auto-generate migration if models changed, then apply
echo -e "${GRAY}  Checking for model changes...${NC}"
cd "$PROJECT_ROOT/backend"

AUTO_GEN_OUTPUT=$("$PYTHON_EXE" -m alembic revision --autogenerate -m "auto" 2>&1 || true)
if echo "$AUTO_GEN_OUTPUT" | grep -q "No changes in schema detected"; then
    echo -e "${GRAY}  No new model changes detected.${NC}"
elif [ $? -eq 0 ]; then
    echo -e "${GREEN}  New migration generated.${NC}"
fi

echo -e "${YELLOW}  Running database migrations...${NC}"
if "$PYTHON_EXE" -m alembic upgrade head 2>&1; then
    echo -e "${GREEN}  Migrations applied successfully.${NC}"
else
    echo -e "${YELLOW}  WARNING: Migrations failed. Ensure the database is running and .env is configured.${NC}"
fi

cd "$PROJECT_ROOT"

# ---------------------------------------------------------------
# Ensure test scaffolding exists
# ---------------------------------------------------------------
echo -e "${YELLOW}[7/7] Ensuring test infrastructure...${NC}"

# Backend tests directory
BACKEND_TESTS_DIR="$PROJECT_ROOT/backend/tests"
if [ ! -d "$BACKEND_TESTS_DIR" ]; then
    mkdir -p "$BACKEND_TESTS_DIR"
    echo -e "${GREEN}  Created backend/tests/${NC}"
fi
if [ ! -f "$BACKEND_TESTS_DIR/__init__.py" ]; then
    touch "$BACKEND_TESTS_DIR/__init__.py"
    echo -e "${GREEN}  Created backend/tests/__init__.py${NC}"
fi

# Verify pytest.ini exists
if [ ! -f "$PROJECT_ROOT/backend/pytest.ini" ]; then
    echo -e "${YELLOW}  WARNING: backend/pytest.ini missing. Tests may not run correctly.${NC}"
else
    echo -e "${GREEN}  backend/pytest.ini present.${NC}"
fi

# Verify vitest config exists
if [ ! -f "$PROJECT_ROOT/frontend/vitest.config.ts" ]; then
    echo -e "${YELLOW}  WARNING: frontend/vitest.config.ts missing. Tests may not run correctly.${NC}"
else
    echo -e "${GREEN}  frontend/vitest.config.ts present.${NC}"
fi

echo -e "${GREEN}  Test infrastructure ready.${NC}"

# ---------------------------------------------------------------
# Done!
# ---------------------------------------------------------------
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${CYAN}Next steps:${NC}"
NEXT_STEP=1
if [ "$ENV_CREATED" = true ]; then
    echo -e "${WHITE}  $NEXT_STEP. Edit .env with your real API keys:${NC}"
    echo -e "${GRAY}     - GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (required for login)${NC}"
    echo -e "${GRAY}     - OPENAI_API_KEY${NC}"
    echo ""
    NEXT_STEP=$((NEXT_STEP + 1))
    echo -e "${WHITE}  $NEXT_STEP. Create 'talk_to_folder' database if not done${NC}"
    echo ""
    NEXT_STEP=$((NEXT_STEP + 1))
fi
if [ "$ENV_PROD_CREATED" = true ]; then
    echo -e "${WHITE}  $NEXT_STEP. Edit .env.production with your Supabase connection string:${NC}"
    echo -e "${GRAY}     - DATABASE_URL (Session Pooler URL from Supabase dashboard)${NC}"
    echo -e "${GRAY}     - Plus all production API keys (Google, OpenAI, etc.)${NC}"
    echo ""
    NEXT_STEP=$((NEXT_STEP + 1))
fi
echo -e "${WHITE}  $NEXT_STEP. Run the app: ./run.sh${NC}"
echo ""
