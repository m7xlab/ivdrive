"""backfill charging session types

Revision ID: f493b86626a
Revises: 952353be8fb7
Create Date: 2026-03-21 16:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'f493b86626a'
down_revision: Union[str, None] = '952353be8fb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill charging_type in charging_sessions based on charging_states
    # We match sessions with charging states that overlap in time
    op.execute("""
    UPDATE charging_sessions cs
    SET charging_type = css.charge_type
    FROM charging_states css
    WHERE cs.user_vehicle_id = css.user_vehicle_id
      AND css.charge_type IS NOT NULL 
      AND css.charge_type != ''
      AND cs.charging_type IS NULL
      AND (
        -- Match sessions that started during a charging state
        (cs.session_start >= css.first_date AND cs.session_start <= css.last_date)
        OR
        -- Match sessions that ended during a charging state  
        (cs.session_end >= css.first_date AND cs.session_end <= css.last_date)
        OR
        -- Match sessions that encompass a charging state
        (cs.session_start <= css.first_date AND cs.session_end >= css.last_date)
      )
    """)


def downgrade() -> None:
    # We don't revert the backfill as it would lose legitimate data
    pass