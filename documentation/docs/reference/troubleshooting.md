---
sidebar_position: 3
title: Troubleshooting
---

# Troubleshooting

## Login & account

| Problem | Fix |
|---------|-----|
| Invite required | Request via `/register` or use a valid invite token |
| Forgot password | Use **Forgot password** on login |
| Lost 2FA device | Use recovery codes |
| Cookies rejected | Ensure HTTPS in production (`COOKIE_SECURE`) |

## Vehicle data

| Problem | Fix |
|---------|-----|
| **Stale / Down** badge | Press Refresh; check Connect login in MyŠkoda app |
| Connect password fails | Reset in MyŠkoda; avoid CAPTCHA lockouts |
| No trips appear | Wait for collector cycles; verify vehicle has trips |
| Range missing | Needs recent drive range samples |

## Self-host

| Problem | Fix |
|---------|-----|
| API unhealthy | `docker compose logs ivdrive-api` |
| Web 502 | Check `NEXT_PUBLIC_API_INTERNAL` and API container |
| DB migrations error | `alembic upgrade head` after backup |
| Email not sending | Verify SMTP_* values and provider allowlist |
| Landing can’t proxy | Ensure `ivdrive-web` hostname resolves on the compose network |

## Landing (production)

| Problem | Fix |
|---------|-----|
| `/` shows app not marketing | Clear `iv_view=app`; check Caddy matchers |
| Mobile shows marketing | Set `iv_view=landing` if intentional; check UA rules |
| Assets 404 | Confirm static export copied into image `/srv` |

## Getting help

1. Check logs (`docker compose logs`)
2. Search [Issues](https://github.com/m7xlab/iVDrive/issues)
3. Ask in [Discussions](https://github.com/m7xlab/iVDrive/discussions)
4. Report security issues via [SECURITY.md](https://github.com/m7xlab/iVDrive/blob/main/SECURITY.md) — not public issues
