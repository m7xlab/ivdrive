# iVDrive Landing

Premium marketing site for iVDrive. Static Next.js export + Caddy reverse proxy.

## What it does

- Serves the marketing pages (`/`, `/features`, `/open-source`, `/community`, `/about`)
- Reverse-proxies the real app (`/login`, `/register`, `/api`, console, assets) to `ivdrive-web:3000`
- Dual-use `/`:
  - Desktop + no auth cookies → marketing landing
  - Mobile UA, auth cookies, or `iv_view=app` → app console
  - `iv_view=landing` forces the marketing page
  - Crawlers see the marketing page (SEO)

Self-hosters **do not need this service**. Run the normal stack and open the web UI directly.

## Develop

```bash
npm install
npm run dev          # http://localhost:3040
npm run build        # static export to ./out
```

`/login` and `/register` are **not** in the static export — in production Caddy proxies them to the app.

## Production

From the repo root:

```bash
docker compose -f docker-compose.yml -f docker-compose.landing.yml up -d --build
```

Landing listens on port `80` and must reach `ivdrive-web` on the shared `backend` compose network.

If another reverse proxy terminates TLS in front, forward the original `Host` and `X-Forwarded-Proto`.

## Cookie switches

| Cookie | Effect |
|---|---|
| `access_token` / `refresh_token` | `/` goes to the app console |
| `iv_view=app` | Always skip marketing |
| `iv_view=landing` | Always show marketing (even mobile) |
