"""Add efficiency calibration fields to user_vehicles."""

from alembic import op
import sqlalchemy as sa


revision = "a3b7c2d1e9f5"
down_revision = "f493b86626a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_vehicles", sa.Column("charger_power_kw", sa.Float(), nullable=True))
    op.add_column("user_vehicles", sa.Column("ice_l_per_100km", sa.Float(), nullable=True))
    op.add_column("user_vehicles", sa.Column("uphill_kwh_per_100km_per_100m", sa.Float(), nullable=True))
    op.add_column("user_vehicles", sa.Column("downhill_kwh_per_100km_per_100m", sa.Float(), nullable=True))
    op.add_column("user_vehicles", sa.Column("speed_city_threshold_kmh", sa.Float(), nullable=True))
    op.add_column("user_vehicles", sa.Column("speed_highway_threshold_kmh", sa.Float(), nullable=True))
    op.add_column("user_vehicles", sa.Column("temp_cold_max_celsius", sa.Float(), nullable=True))
    op.add_column("user_vehicles", sa.Column("temp_optimal_min_celsius", sa.Float(), nullable=True))
    op.add_column("user_vehicles", sa.Column("temp_optimal_max_celsius", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_vehicles", "charger_power_kw")
    op.drop_column("user_vehicles", "ice_l_per_100km")
    op.drop_column("user_vehicles", "uphill_kwh_per_100km_per_100m")
    op.drop_column("user_vehicles", "downhill_kwh_per_100km_per_100m")
    op.drop_column("user_vehicles", "speed_city_threshold_kmh")
    op.drop_column("user_vehicles", "speed_highway_threshold_kmh")
    op.drop_column("user_vehicles", "temp_cold_max_celsius")
    op.drop_column("user_vehicles", "temp_optimal_min_celsius")
    op.drop_column("user_vehicles", "temp_optimal_max_celsius")