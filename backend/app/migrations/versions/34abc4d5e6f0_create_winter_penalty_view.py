"""create v_winter_penalty_stats view

Revision ID: 34abc4d5e6f0
Revises: 33abc4d5e6f9
Create Date: 2026-04-18 17:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '34abc4d5e6f0'
down_revision: Union[str, None] = '33abc4d5e6f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE VIEW v_winter_penalty_stats AS
    SELECT 
        d.user_vehicle_id,
        ROUND(dc.temperature_celsius::numeric) AS temperature,
        AVG(dc.consumption) AS avg_consumption,
        COUNT(dc.id) AS data_points
    FROM 
        drive_consumptions dc
    JOIN 
        drives d ON dc.drive_id = d.id
    WHERE 
        dc.temperature_celsius IS NOT NULL
        AND dc.consumption IS NOT NULL
    GROUP BY 
        d.user_vehicle_id, 
        ROUND(dc.temperature_celsius::numeric);
    """)

def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_winter_penalty_stats;")
