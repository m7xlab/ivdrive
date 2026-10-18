---
sidebar_position: 5
title: Upgrades
---

# Upgrades

Keep self-hosted iVDrive current.

## Standard upgrade

```bash
cd iVDrive
git pull
docker compose build
docker compose up -d
```

## Database migrations

After pulling a version that includes migrations:

```bash
docker compose exec ivdrive-api env PYTHONPATH=/app alembic upgrade head
```

Check the repository `CHANGELOG.md` for version notes.

## Backups

Before major upgrades, back up:

1. PostgreSQL volume (`data/postgresql`)
2. `.env` secrets
3. Any object storage buckets you configured

```bash
docker compose exec postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
```

## Rollback

Keep the previous image tags and restore the database dump if needed.

## Tips

- Read `CHANGELOG.md` for breaking changes
- Test on a staging copy when possible
- Pin image tags in production if you prefer strict control
