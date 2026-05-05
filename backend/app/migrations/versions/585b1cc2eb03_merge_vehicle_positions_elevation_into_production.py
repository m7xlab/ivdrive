"""merge vehicle_positions composite index branch back to main (battery SoH) line

Revision ID: 585b1cc2eb03
Revises: d1e2f3a4bb5c, f36d25e55dd8
Create Date: 2026-05-04 22:05:00.000000

Merge of:
- d1e2f3a4bb5c: add index on vehicle_positions for elevation lookups
              (down_revision: a1b2c3d4e5f8 -> composite index branch)
- f36d25e55dd8: add_battery_soh_estimates_table_v2 (main line)

Branch tree resolution: The vehicle_positions index migrations were merged
back into the main line at the same revision as battery SoH v2.
"""


# revision identifiers, used by Alembic.
revision: str = '585b1cc2eb03'
down_revision: tuple = ('d1e2f3a4bb5c', 'f36d25e55dd8')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
