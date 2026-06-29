"""Add Battery SoH Ops Model — estimates, alerts, tier config.

Battery Health Passport feature (v1.2.0). Five tables:

1. battery_soh_estimates — append-only history of SoH calculations
   - method: 'capacity' | 'throughput' | 'resistance' | 'aggregate'
   - soh_pct: percent (0-110, capped by validation)
   - estimated_kwh: derived full-pack capacity
   - sample_count, inputs_json, anomalies_json for auditability
   - confidence: 'high' | 'medium' | 'low'

2. battery_soh_alerts — anomaly conditions (sudden drop, degradation accel)
   - severity: 'info' | 'warn' | 'critical'
   - acknowledged_at: NULL = open, set = dismissed by user/admin

3. battery_tier_configs — per-tier defaults (mirrors ai_tier_configs)
   - free / plus / pro
   - pdf_enabled, alerts_enabled, estimate_frequency, min_confidence_required
   - monthly_price_eur placeholder (0 until pricing decided)

4. battery_user_overrides — admin per-user overrides
   - NULL fields = use tier default

5. battery_soh_usage_log — usage tracking for billing + admin visibility
   - every estimate generation, PDF send, alert fired

Revision ID: a1b2c3d4e5g7
Revises: b2c3d4e5f6a8
Create Date: 2026-06-24 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5g7"
down_revision: Union[str, None] = "b2c3d4e5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. battery_soh_estimates — append-only SoH history
    op.execute("""
        CREATE TABLE IF NOT EXISTS battery_soh_estimates (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_vehicle_id     UUID NOT NULL REFERENCES user_vehicles(id) ON DELETE CASCADE,
            estimated_at        TIMESTAMPTZ NOT NULL,
            method              VARCHAR(30) NOT NULL
                                CHECK (method IN ('capacity', 'throughput', 'resistance', 'aggregate')),
            soh_pct             NUMERIC(5, 2) NOT NULL,
            estimated_kwh       NUMERIC(6, 2),
            sample_count        INTEGER,
            inputs_json         JSONB,
            anomalies_json      JSONB,
            confidence          VARCHAR(10)
                                CHECK (confidence IS NULL OR confidence IN ('high', 'medium', 'low')),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_battery_soh_estimates_vehicle_time ON battery_soh_estimates(user_vehicle_id, estimated_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_battery_soh_estimates_method ON battery_soh_estimates(method);")

    # 2. battery_soh_alerts — anomaly conditions
    op.execute("""
        CREATE TABLE IF NOT EXISTS battery_soh_alerts (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_vehicle_id     UUID NOT NULL REFERENCES user_vehicles(id) ON DELETE CASCADE,
            alert_type          VARCHAR(50) NOT NULL
                                CHECK (alert_type IN ('sudden_drop', 'degradation_acceleration', 'low_confidence', 'invalid_data')),
            severity            VARCHAR(10) NOT NULL
                                CHECK (severity IN ('info', 'warn', 'critical')),
            soh_before          NUMERIC(5, 2),
            soh_after           NUMERIC(5, 2),
            delta_pct           NUMERIC(5, 2),
            message             TEXT,
            detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            acknowledged_at     TIMESTAMPTZ,
            acknowledged_by     UUID REFERENCES users(id) ON DELETE SET NULL
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_battery_soh_alerts_vehicle ON battery_soh_alerts(user_vehicle_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_battery_soh_alerts_open ON battery_soh_alerts(user_vehicle_id) WHERE acknowledged_at IS NULL;")

    # 3. battery_tier_configs — per-tier defaults (mirror ai_tier_configs)
    op.execute("""
        CREATE TABLE IF NOT EXISTS battery_tier_configs (
            tier                      VARCHAR(20) PRIMARY KEY
                                       CHECK (tier IN ('free', 'plus', 'pro')),
            pdf_enabled               BOOLEAN NOT NULL DEFAULT FALSE,
            alerts_enabled            BOOLEAN NOT NULL DEFAULT FALSE,
            resale_calc_enabled       BOOLEAN NOT NULL DEFAULT FALSE,
            estimate_frequency        VARCHAR(20) NOT NULL DEFAULT 'weekly'
                                       CHECK (estimate_frequency IN ('daily', 'weekly', 'monthly')),
            min_confidence_required   VARCHAR(10) NOT NULL DEFAULT 'medium'
                                       CHECK (min_confidence_required IN ('low', 'medium', 'high')),
            monthly_price_eur         NUMERIC(8, 2) NOT NULL DEFAULT 0,
            description               TEXT NOT NULL DEFAULT '',
            updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # Seed tier configs with beta defaults (price 0, all features OFF for free, ON for plus/pro)
    op.execute("""
        INSERT INTO battery_tier_configs
          (tier, pdf_enabled, alerts_enabled, resale_calc_enabled, estimate_frequency, min_confidence_required, monthly_price_eur, description)
        VALUES
          ('free', FALSE, FALSE, TRUE,  'weekly',  'medium', 0,
            'Free tier: live dashboard only. No PDF, no alerts.'),
          ('plus', TRUE,  TRUE,  TRUE,  'daily',   'medium', 0,
            'Plus tier: monthly Passport PDF, alerts, resale calc. €5/mo (placeholder).'),
          ('pro',  TRUE,  TRUE,  TRUE,  'daily',   'low',    0,
            'Pro tier: everything in Plus, faster estimates, lower confidence threshold. €12/mo (placeholder).')
        ON CONFLICT (tier) DO NOTHING;
    """)

    # 4. battery_user_overrides — per-user overrides (mirror ai_user_overrides)
    op.execute("""
        CREATE TABLE IF NOT EXISTS battery_user_overrides (
            user_id                  UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            tier_override            VARCHAR(20)
                                     CHECK (tier_override IS NULL OR tier_override IN ('free', 'plus', 'pro')),
            pdf_enabled_override     BOOLEAN,
            alerts_enabled_override  BOOLEAN,
            note                     TEXT,
            updated_by_user_id       UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # 5. battery_soh_usage_log — usage tracking (mirror ai_usage_log)
    op.execute("""
        CREATE TABLE IF NOT EXISTS battery_soh_usage_log (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             UUID REFERENCES users(id) ON DELETE CASCADE,
            user_vehicle_id     UUID REFERENCES user_vehicles(id) ON DELETE SET NULL,
            event_type          VARCHAR(30) NOT NULL
                                CHECK (event_type IN ('estimate_generated', 'pdf_sent', 'alert_fired', 'admin_override', 'tier_change')),
            event_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            soh_pct             NUMERIC(5, 2),
            confidence          VARCHAR(10),
            metadata_json       JSONB
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_battery_soh_usage_log_user_time ON battery_soh_usage_log(user_id, event_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_battery_soh_usage_log_vehicle_time ON battery_soh_usage_log(user_vehicle_id, event_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_battery_soh_usage_log_event_type ON battery_soh_usage_log(event_type);")

    # 6. Row-level security — users see their own vehicle data, admins see all
    op.execute("ALTER TABLE battery_soh_estimates ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE battery_soh_alerts ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE battery_soh_usage_log ENABLE ROW LEVEL SECURITY;")

    op.execute("""
        CREATE POLICY isolate_battery_soh_estimates ON battery_soh_estimates
            FOR ALL
            USING (user_vehicle_id IN (
                SELECT id FROM user_vehicles
                WHERE user_id = (current_setting('app.current_user_id', true))::uuid
            ));
    """)
    op.execute("""
        CREATE POLICY isolate_battery_soh_alerts ON battery_soh_alerts
            FOR ALL
            USING (user_vehicle_id IN (
                SELECT id FROM user_vehicles
                WHERE user_id = (current_setting('app.current_user_id', true))::uuid
            ));
    """)
    op.execute("""
        CREATE POLICY isolate_battery_soh_usage_log ON battery_soh_usage_log
            FOR ALL
            USING (user_id = (current_setting('app.current_user_id', true))::uuid);
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS isolate_battery_soh_usage_log ON battery_soh_usage_log;")
    op.execute("DROP POLICY IF EXISTS isolate_battery_soh_alerts ON battery_soh_alerts;")
    op.execute("DROP POLICY IF EXISTS isolate_battery_soh_estimates ON battery_soh_estimates;")

    op.execute("ALTER TABLE battery_soh_usage_log DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE battery_soh_alerts DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE battery_soh_estimates DISABLE ROW LEVEL SECURITY;")

    op.execute("DROP TABLE IF EXISTS battery_soh_usage_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS battery_user_overrides CASCADE;")
    op.execute("DROP TABLE IF EXISTS battery_tier_configs CASCADE;")
    op.execute("DROP TABLE IF EXISTS battery_soh_alerts CASCADE;")
    op.execute("DROP TABLE IF EXISTS battery_soh_estimates CASCADE;")