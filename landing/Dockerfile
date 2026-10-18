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

# ── Caddy: serve static + proxy app paths ───────────────────────────────
FROM caddy:2.8-alpine

COPY --from=builder /app/out /srv
COPY caddy/Caddyfile /etc/caddy/Caddyfile

EXPOSE 80
