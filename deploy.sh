#!/usr/bin/env bash
# deploy.sh — Build and push the Tenex container to Azure Container Registry
# Usage: ./deploy.sh

set -e
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Colors
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Load .env.deploy
ENV_FILE="$PROJECT_ROOT/.env.deploy"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Missing $ENV_FILE - copy .env.deploy.example and fill in values${NC}"
    exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

REGISTRY="${ACR_REGISTRY:?ACR_REGISTRY not set in .env.deploy}"
ACR_USERNAME="${ACR_USERNAME:?ACR_USERNAME not set in .env.deploy}"
ACR_PASSWORD="${ACR_PASSWORD:?ACR_PASSWORD not set in .env.deploy}"
IMAGE="$REGISTRY/tenex:latest"
TOTAL_STEPS=4
STEP=0
START_TIME=$(date +%s)

write_step() {
    STEP=$((STEP + 1))
    echo -e "\n${CYAN}[$STEP/$TOTAL_STEPS] $1${NC}"
}

# -- Tests -------------------------------------------------------------------
write_step "Running tests"
"$PROJECT_ROOT/test.sh"

# -- Bump version ------------------------------------------------------------
write_step "Bumping version"
(cd "$PROJECT_ROOT/frontend" && npm version patch --no-git-tag-version) >/dev/null
NEW_VERSION=$(cd "$PROJECT_ROOT/frontend" && node -p "require('./package.json').version")
echo -e "${GREEN}  v$NEW_VERSION${NC}"

# -- Docker build ------------------------------------------------------------
write_step "Building Docker image"

echo "$ACR_PASSWORD" | docker login "$REGISTRY" -u "$ACR_USERNAME" --password-stdin >/dev/null 2>&1
echo "  Logged in to ACR"

BUILD_OUT=$(docker build -t "$IMAGE" -f Dockerfile --quiet . 2>&1) || BUILD_EXIT=$?
if [ "${BUILD_EXIT:-0}" -ne 0 ]; then
    echo -e "${YELLOW}  Build failed - pruning Docker build cache and retrying...${NC}"
    docker builder prune -f >/dev/null 2>&1 || true
    BUILD_OUT=$(docker build -t "$IMAGE" -f Dockerfile --quiet . 2>&1) || {
        echo -e "\n${YELLOW}--- Docker build output ---${NC}"
        echo "$BUILD_OUT"
        echo -e "${RED}Docker build failed${NC}"
        exit 1
    }
fi
echo -e "${GREEN}  Image built${NC}"

# -- Docker push -------------------------------------------------------------
write_step "Pushing to ACR"

PUSH_OUT=$(docker push "$IMAGE" 2>&1) || {
    echo "$PUSH_OUT"
    echo -e "${RED}Docker push failed${NC}"
    exit 1
}
echo -e "${GREEN}  Pushed $IMAGE${NC}"

# -- Done --------------------------------------------------------------------
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
MINS=$((ELAPSED / 60))
SECS=$((ELAPSED % 60))

echo ""
echo -e "${GREEN}Deploy complete (${MINS}m ${SECS}s)${NC}"
echo "  Image: $IMAGE"
echo "  Restart the App Service from Azure Portal."
echo ""
