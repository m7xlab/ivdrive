# ── Build static marketing site ─────────────────────────────────────────
FROM node:24-alpine AS builder
WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build && \
    # Also expose /page/ URLs (trailing slash) for static export
    for p in features open-source community about roadmap sponsors; do \
      mkdir -p "out/$p" && cp "out/$p.html" "out/$p/index.html"; \
    done

# ── Caddy: serve static + proxy app paths ───────────────────────────────
FROM caddy:2.8-alpine

COPY --from=builder /app/out /srv
COPY caddy/Caddyfile /etc/caddy/Caddyfile

EXPOSE 80
