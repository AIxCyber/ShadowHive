# ── Stage 1: Production ─────────────────────────────────────────────────────
FROM node:22-alpine AS prod

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --only=production

COPY . .
RUN npm run build

# Non-root user for security
RUN addgroup -S shadowhive && adduser -S shadowhive -G shadowhive
USER shadowhive

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

ENV HOST=0.0.0.0
ENV PORT=3000
ENV NODE_ENV=production

CMD ["npm", "run", "start"]

# ── Stage 2: Development ──────────────────────────────────────────────────────
FROM node:22-alpine AS dev

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
