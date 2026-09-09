# Node 24.20.0 / npm 11.19.0 / Alpine 3.24.1 — multi-arch index (amd64 + arm64).
# Bump digest only after: docker buildx imagetools inspect node:24-alpine
FROM node:24-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS base

FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app
COPY package.json package-lock.json* ./
# react-leaflet@5 peers React 19; we are still on React 18. Drop this flag in the
# React 19 upgrade (PLAN-frontend-version-upgrade-v1.md Phase 2). Not Tremor.
RUN npm install --legacy-peer-deps

FROM base AS builder
# NEXT_PUBLIC_* env vars must be inlined by `next build` at build time, not
# runtime. Declared as ARG here and exported as ENV so `next build` sees them;
# the same names must also be passed via `build.args` in docker-compose.yml
# for the ivdrive-web service (or via `--build-arg` on `docker build`).
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY=$NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
