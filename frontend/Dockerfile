FROM node:22-alpine AS base

FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app
COPY package.json package-lock.json* ./
# We MUST use --legacy-peer-deps because Tremor doesn't officially support React 19 yet
RUN npm install --legacy-peer-deps

FROM base AS builder
# NEXT_PUBLIC_* env vars must be inlined by `next build` at build time, not
# runtime. Declared as ARG here and exported as ENV so `next build` sees them;
# the same names must also be passed via `build.args` in docker-compose.yml
# for the ivdrive-web service (or via `--build-arg` on `docker build`).
ARG NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY
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
