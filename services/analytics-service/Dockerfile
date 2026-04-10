# =============================================================
# NexusStream — Analytics Service Dockerfile (Production)
# =============================================================
# Multi-stage build:
#   Stage 1 (builder) — installs Python deps with GCC available
#   Stage 2 (final)   — minimal runtime, no build tools
#
# Security: non-root user "nexus", no shell access needed.

# ---------------------------------------------------------
# Stage 1: Build — install Python dependencies
# ---------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# gcc required for some C extensions (e.g. uvloop in uvicorn[standard])
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install all deps (including test deps for the test stage)
# --prefix puts them in /install for clean copying
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------
# Stage 2: Runtime — minimal image
# ---------------------------------------------------------
FROM python:3.11-slim AS final

# Create non-root user
RUN useradd -r -s /bin/false nexus

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY main.py .
COPY conftest.py .
COPY pyproject.toml .
COPY app/ ./app/
COPY config/ ./config/
COPY tests/ ./tests/

# Set correct ownership
RUN chown -R nexus:nexus /app

USER nexus

EXPOSE 8001

# Liveness health check — Docker restarts container if this fails 3× in a row
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

# Start uvicorn with optimal workers for I/O-bound async workloads
# worker_class=uvicorn.workers.UvicornWorker with gunicorn for multi-core:
#   CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8001"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", \
     "--no-access-log", "--loop", "uvloop"]
