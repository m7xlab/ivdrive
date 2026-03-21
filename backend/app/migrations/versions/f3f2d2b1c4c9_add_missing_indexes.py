"""add missing indexes

Revision ID: f3f2d2b1c4c9
Revises: f493b86626a
Create Date: 2026-03-21 22:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f3f2d2b1c4c9'
down_revision = 'f493b86626a'
branch_labels = None
depends_on = None

def upgrade():
    # Performance indexes based on PR Agent review
    op.create_index(
        'ix_charging_sessions_user_vehicle_id_actual_cost',
        'charging_sessions',
        ['user_vehicle_id', 'actual_cost_eur', 'energy_kwh']
    )

def downgrade():
    op.drop_index('ix_charging_sessions_user_vehicle_id_actual_cost', table_name='charging_sessions')
