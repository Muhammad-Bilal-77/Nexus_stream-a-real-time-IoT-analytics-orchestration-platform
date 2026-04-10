# ============================================================
# NexusStream — Ingestion Service Dockerfile
# ============================================================
# Multi-stage build:
#   Stage 1 (deps)  — install only production dependencies
#   Stage 2 (final) — copy app + deps into minimal runtime image
#
# Why multi-stage?
#   - Keeps the final image lean (no devDependencies, no npm cache)
#   - Reduces attack surface (smaller image = fewer CVEs)
#   - Separates build-time tools from runtime

# -----------------------------------------------------------
# Stage 1: Install production dependencies
# -----------------------------------------------------------
FROM node:20-alpine AS deps

WORKDIR /app

# Copy manifests first to leverage Docker layer cache
# Rebuild node_modules only when package*.json changes
COPY package.json package-lock.json* ./

# Install ONLY production deps — omit devDependencies in final image
RUN npm ci --omit=dev --ignore-scripts

# -----------------------------------------------------------
# Stage 2: Final runtime image
# -----------------------------------------------------------
FROM node:20-alpine AS final

# Security: run as non-root user
RUN addgroup -S nexus && adduser -S nexus -G nexus

WORKDIR /app

# Copy production node_modules from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy application source
COPY src/ ./src/
COPY config/ ./config/

# Set ownership for non-root user
RUN chown -R nexus:nexus /app

USER nexus

# Document the port — does NOT publish; use docker-compose for that
EXPOSE 3001

# Health check — Docker monitors this and restarts if unhealthy
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3001/health || exit 1

# Start the service
CMD ["node", "src/index.js"]
