# =============================================================
# NexusStream — Auth Service Dockerfile
# =============================================================

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev --ignore-scripts

FROM node:20-alpine AS final
RUN addgroup -S nexus && adduser -S nexus -G nexus
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY src/ ./src/
COPY config/ ./config/
RUN chown -R nexus:nexus /app
USER nexus

EXPOSE 3002

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3002/health || exit 1

CMD ["node", "src/index.js"]
