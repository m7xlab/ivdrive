#!/bin/bash
set -e

echo "🚀 Starting iVDrive Database Migration (v1.0.20.1)..."

# Ensure we're in the right directory
cd "$(dirname "$0")"

# Wait for database container to be healthy
echo "⏳ Checking database health..."
until docker inspect -f {{.State.Health.Status}} ivdrive-postgres-1 | grep -q "healthy"; do
    sleep 2;
done

# Run Alembic Upgrade in the API container
echo "🔄 Upgrading Alembic Database schema to head..."
docker exec -w /app ivdrive-ivdrive-api-1 bash -c "PYTHONPATH=. alembic upgrade head"

echo "✅ Database schema upgrade complete!"
