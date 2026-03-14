
import os
import sqlalchemy

DATABASE_URL = "postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}".format(
    user="ivdrive",
    password="n7-JMYT0HZkusbvPev1bUhltKcPtgsGM",
    host="postgres",
    port="5432",
    db="ivdrive",
)

try:
    engine = sqlalchemy.create_engine(DATABASE_URL)
    with engine.connect() as connection:
        # Check if the row exists before updating
        result = connection.execute(sqlalchemy.text("SELECT 1 FROM alembic_version WHERE version_num = '1a2b3c4d5e6f'"))
        if result.scalar_one_or_none() is not None:
            trans = connection.begin()
            connection.execute(sqlalchemy.text("UPDATE alembic_version SET version_num = 'e0299bdbb5d2' WHERE version_num = '1a2b3c4d5e6f'"))
            trans.commit()
            print("Database version updated successfully from 1a2b3c4d5e6f to e0299bdbb5d2.")
        else:
            print("Version 1a2b3c4d5e6f not found in alembic_version table. No update needed.")

except Exception as e:
    print(f"An error occurred: {e}")

