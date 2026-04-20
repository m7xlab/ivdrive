"""add_indexes_for_union_pagination

Revision ID: 31abc4d5e6f7
Revises: 30fea49a7f15
Create Date: 2026-04-16 11:20:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '31abc4d5e6f7'
down_revision: Union[str, None] = '30fea49a7f15'

def upgrade() -> None:
    # Index for VehiclePosition (user_vehicle_id, captured_at)
    op.create_index('ix_vp_vehicle_captured_at', 'vehicle_positions', ['user_vehicle_id', 'captured_at'])
    
    # Index for ChargingSession (user_vehicle_id, session_start)
    op.create_index('ix_cs_vehicle_session_start', 'charging_sessions', ['user_vehicle_id', 'session_start'])


def downgrade() -> None:
    op.drop_index('ix_cs_vehicle_session_start', table_name='charging_sessions')
    op.drop_index('ix_vp_vehicle_captured_at', table_name='vehicle_positions')
