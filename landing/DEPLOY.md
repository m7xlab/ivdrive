# Deploying the marketing landing (v1.2.0)

How Caddy fits in, how to test locally, and how to update production.

**Do not put internal hostnames, IPs, SSH users, or private paths in this file.**

## Architecture

```
                    ┌─────────────────────────────┐
 Internet ────────► │  ivdrive-landing (Caddy)    │
                    │  :80 / :443                 │
                    │                             │
                    │  static marketing pages     │
                    │  /  /features  /roadmap …   │
                    │  /docs ──► ivdrive-docs     │
                    │                             │
                    │  everything else            │
                    │  /login /register /api …    │
                    │  console paths              │
                    │        │                    │
                    │        ▼                    │
                    │  reverse_proxy              │
                    │  ivdrive-web:3000           │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │  Normal iVDrive stack       │
                    │  web · api · collector ·    │
                    │  postgres · valkey          │
                    └─────────────────────────────┘
```

### Dual routing on `/` (Caddy)

| Request | Served |
|---------|--------|
| Desktop, no auth cookies | **Landing** marketing home |
| `access_token` / `refresh_token` cookie | **App console** (proxied) |
| `iv_view=app` cookie | **App console** |
| `iv_view=landing` cookie | **Landing** (override) |
| Mobile UA | **App console** |
| Googlebot / crawlers | **Landing** |

### Self-host (no landing)

Unchanged: `docker compose up` → console at `http://host:3000`. Caddy is **not** required.

---

## Local test (production-like)

From the repo root:

```bash
docker compose -f docker-compose.yml -f docker-compose.landing.yml up -d --build
```

| Check | Expect |
|-------|--------|
| `http://localhost/` | Landing (desktop, clear cookies) |
| `http://localhost/roadmap` | Roadmap page |
| `http://localhost/docs/` | Docs |
| `http://localhost/login` | App login (proxied) |
| `curl -A iPhone http://localhost/` | App |
| `curl -H "Cookie: access_token=x" http://localhost/` | App |

**Cookie note (local QA):** browsers share cookies across ports on `localhost`. If you signed into the app on `:3000`, another port may show the console. Clear `access_token` / `refresh_token` to see the landing.

---

## Production update

Use **your** deploy host and directory (keep those out of git).

```bash
# On the production host — clone/pull the release branch
git fetch && git checkout Update/v1.2.0 && git pull

# Build + start landing + docs next to the existing stack
docker compose -f docker-compose.yml -f docker-compose.landing.yml up -d --build
```

`ivdrive-landing` publishes **:80** by default. If the host already owns :80, change the mapping in `docker-compose.landing.yml`:

```yaml
ports:
  - "3001:80"   # or another free host port
```

### Public entrypoint

| | |
|--|--|
| **Before** | Public hostname → `ivdrive-web:3000` |
| **After** | Public hostname → **`ivdrive-landing` :80** |

If TLS is terminated by an external proxy (reverse proxy, tunnel, load balancer), point it at the landing port. Keep `ivdrive-web` on the Docker network only (not published publicly).

### Smoke test

```bash
curl -sI https://YOUR_HOST/ | head
curl -s https://YOUR_HOST/ | grep -o '<title>[^<]*</title>'
curl -s https://YOUR_HOST/roadmap | grep -o '<title>[^<]*</title>'
curl -sI https://YOUR_HOST/login
curl -sA "Googlebot" https://YOUR_HOST/ | grep -o '<title>[^<]*</title>'
```

### Rollback

```bash
docker compose -f docker-compose.yml -f docker-compose.landing.yml stop ivdrive-landing
# Point the public reverse proxy back to ivdrive-web:3000
```
