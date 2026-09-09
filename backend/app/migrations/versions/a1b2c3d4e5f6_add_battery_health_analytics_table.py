"""add battery_health_analytics table (cache for v2 SoH estimates)

Revision ID: d6e7f8a9b0c1
Revises: 1924fb48a5b1
Create Date: 2026-09-07 06:55:00

Adds the battery_health_analytics table that caches per-method SoH estimates
plus the combined view per vehicle. Used by /api/v1/vehicles/{id}/battery-
health-analytics and the legacy /analytics/battery-health endpoint (cache-
first read with live-compute fallback).

NOTE: Originally shipped with revision id 'a1b2c3d4e5f6', which already
belongs to add_smart_polling_intervals. That collision produced
"Revision a1b2c3d4e5f6 is present more than once" and a second head
beside 1924fb48a5b1 (current production). Re-issued as d6e7f8a9b0c1
on top of 1924fb48a5b1. CREATE TABLE IF NOT EXISTS keeps this safe
on DBs that already have the table from the Aug 5 raw-SQL work.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d6e7f8a9b0c1"
down_revision = "1924fb48a5b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS battery_health_analytics (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_vehicle_id uuid NOT NULL
                REFERENCES user_vehicles(id) ON DELETE CASCADE,
            computed_at     timestamp with time zone NOT NULL,
            method          varchar(50) NOT NULL,
            soh_pct         numeric(5,2) NOT NULL,
            estimated_kwh   numeric(6,2),
            sample_count    integer,
            confidence      varchar(10),
            inputs_json     jsonb,
            extra_json      jsonb,
            created_at      timestamp with time zone NOT NULL DEFAULT now(),
            CONSTRAINT bha_method_check CHECK (
                method IN (
                    'tesla_capacity', 'charging_curve_taper', 'cell_imbalance',
                    'throughput', 'fleet_benchmark', 'range_drift_over_time',
                    'combined'
                )
            ),
            CONSTRAINT bha_confidence_check CHECK (
                confidence IS NULL OR confidence IN ('high', 'medium', 'low')
            )
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_bha_method ON battery_health_analytics (method)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_bha_vehicle_time "
        "ON battery_health_analytics (user_vehicle_id, computed_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_bha_vehicle_method_time "
        "ON battery_health_analytics (user_vehicle_id, method, computed_at DESC)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_bha_vehicle_method_computed "
        "ON battery_health_analytics (user_vehicle_id, method, computed_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_bha_vehicle_method_computed")
    op.execute("DROP INDEX IF EXISTS ix_bha_vehicle_method_time")
    op.execute("DROP INDEX IF EXISTS ix_bha_vehicle_time")
    op.execute("DROP INDEX IF EXISTS ix_bha_method")
    op.execute("DROP TABLE IF EXISTS battery_health_analytics")
