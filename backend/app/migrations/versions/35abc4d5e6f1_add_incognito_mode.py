"""add incognito mode

Revision ID: 35abc4d5e6f1
Revises: 34abc4d5e6f0
Create Date: 2026-04-19 11:29:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '35abc4d5e6f1'
down_revision = '34abc4d5e6f0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_vehicles', sa.Column('incognito_mode', sa.Boolean(), server_default='false', nullable=False))


def downgrade():
    op.drop_column('user_vehicles', 'incognito_mode')
