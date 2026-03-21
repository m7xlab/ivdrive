"""add energy prices and country code

Revision ID: 709fd0a72bf
Revises: f493b86626a
Create Date: 2026-03-21 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '709fd0a72bf'
down_revision: Union[str, None] = 'f493b86626a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE energy_prices (
            country_code VARCHAR(2) PRIMARY KEY,
            country_name VARCHAR(50) NOT NULL,
            electricity_price_eur_kwh FLOAT NOT NULL,
            petrol_price_eur_l FLOAT NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
        );
        ALTER TABLE user_vehicles ADD COLUMN country_code VARCHAR(2) DEFAULT 'LT' NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE user_vehicles DROP COLUMN country_code;
        DROP TABLE energy_prices;
    """)