---
sidebar_position: 4
title: Landing proxy (optional)
---

# Landing proxy (optional)

For **public production** deployments you can put a marketing site in front of the app without changing self-host UX.

## How it works

The `landing/` service:

1. Serves static marketing pages (`/`, `/features`, …)
2. Reverse-proxies app routes (`/login`, `/api`, console) to `ivdrive-web`
3. Decides on `/`:
   - Desktop guest / crawlers → marketing
   - Mobile or signed-in → app console
   - `iv_view=landing` / `iv_view=app` cookies override

Self-hosters who skip this service still open the console at `/` as usual.

## Enable

```bash
docker compose -f docker-compose.yml -f docker-compose.landing.yml up -d --build
```

Landing listens on port **80** by default. Terminate TLS in front (or extend the Caddyfile).

## Cookie switches

| Cookie | Effect |
|--------|--------|
| `access_token` / `refresh_token` | `/` → app console |
| `iv_view=app` | Always skip marketing |
| `iv_view=landing` | Always show marketing |

## Develop the landing

```bash
cd landing
npm install
npm run dev    # http://localhost:3040
```

See `landing/README.md` for details.
