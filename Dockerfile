# =============================================================================
# Multi-stage Dockerfile for Talk-to-a-Folder
# Stage 1: Build frontend (React + Vite)
# Stage 2: Python backend with built frontend served as static files
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build frontend
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

# Install dependencies first (layer cache)
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

# Copy source and build
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python backend + static frontend
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/ ./

# Copy built frontend into static/ directory for FastAPI to serve
COPY --from=frontend-builder /build/frontend/dist ./static/

# Expose port
EXPOSE 8000

# Run alembic migrations then start uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
