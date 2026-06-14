"""Expand ai_embeddings dimension 384 -> 768 and add provider column.

Switching from deterministic hashing (384-dim) to gemini-embedding-001
(3072-dim default, Matryoshka-truncated to 768 for storage).

This migration:
  1. DROPS all existing embeddings (384-dim are incompatible with 768-dim)
  2. Alters ai_embeddings.embedding from vector(384) to vector(768)
  3. Rebuilds the HNSW index for the new dimension
  4. Adds embedding_provider column so we can A/B between providers later
  5. Adds embedding_model column for tracking which model version produced the vector

Data loss: the 91 summary docs and all trip/charge chunks must be re-embedded.
The full re-vectorization is triggered after this migration via:
  docker exec ivdrive-ivdrive-collector-1 python3 -m app.scripts.embed_all

Revision ID: 8b3c4d5e6f71
Revises: 8b3c4d5e6f70
Create Date: 2026-06-09 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "8b3c4d5e6f71"
down_revision: Union[str, None] = "8b3c4d5e6f70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Wipe all existing embeddings — they are 384-dim, incompatible.
    op.execute("TRUNCATE TABLE ai_embeddings;")

    # 2. Drop the old HNSW index (built on vector(384) operator class).
    op.execute("DROP INDEX IF EXISTS idx_embeddings_embedding;")

    # 3. Resize the column.
    op.execute("ALTER TABLE ai_embeddings ALTER COLUMN embedding TYPE vector(768);")

    # 4. Add provider/model columns (default gemini-embedding-001 going forward).
    op.execute("""
        ALTER TABLE ai_embeddings
          ADD COLUMN IF NOT EXISTS embedding_provider VARCHAR(50) NOT NULL DEFAULT 'gemini-embedding-001',
          ADD COLUMN IF NOT EXISTS embedding_model    VARCHAR(100) NOT NULL DEFAULT 'gemini-embedding-001@768';
    """)

    # 5. Recreate HNSW index on the new dimension.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_embedding
            ON ai_embeddings USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 200);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_embeddings_embedding;")
    op.execute("TRUNCATE TABLE ai_embeddings;")
    op.execute("""
        ALTER TABLE ai_embeddings
          DROP COLUMN IF EXISTS embedding_provider,
          DROP COLUMN IF EXISTS embedding_model;
    """)
    op.execute("ALTER TABLE ai_embeddings ALTER COLUMN embedding TYPE vector(384);")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_embedding
            ON ai_embeddings USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 200);
    """)
