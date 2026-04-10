# =============================================================
# NexusStream — Dashboard Service Dockerfile (Production)
# =============================================================
# Multi-stage build for minimal image size and attack surface.

# ---------------------------------------------------------
# Stage 1: Build — install Python dependencies
# ---------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# gcc required for some C extensions (asyncpg, uvloop)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------
# Stage 2: Runtime — minimal image
# ---------------------------------------------------------
FROM python:3.11-slim AS final

RUN useradd -r -s /bin/false nexus

WORKDIR /app

# Copy installed packages via site-packages
COPY --from=builder /install /usr/local

COPY main.py .
COPY conftest.py .
COPY pyproject.toml .
COPY app/ ./app/
COPY config/ ./config/
COPY tests/ ./tests/
COPY scripts/ ./scripts/

RUN chown -R nexus:nexus /app

USER nexus

EXPOSE 8002

# Liveness health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')" || exit 1

# Start uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", \
     "--no-access-log", "--loop", "uvloop"]
