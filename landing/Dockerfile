# ── Build static marketing site ─────────────────────────────────────────
FROM node:24-alpine AS builder
WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .
# Build static export, then also serve /page/ (trailing slash) for every
# exported page — not a hardcoded route list.
RUN npm run build \
  && for f in out/*.html; do \
       base=$(basename "$f" .html); \
       [ "$base" = "index" ] || [ "$base" = "404" ] && continue; \
       mkdir -p "out/$base" && cp "$f" "out/$base/index.html"; \
     done

# ── Caddy: static marketing + reverse proxy ─────────────────────────────
# Default config is a fallback. Production/self-host should mount their own:
#   - ./landing/caddy/Caddyfile:/etc/caddy/Caddyfile:ro
FROM caddy:2.8-alpine

COPY --from=builder /app/out /srv
COPY caddy/Caddyfile.example /etc/caddy/Caddyfile

EXPOSE 80
