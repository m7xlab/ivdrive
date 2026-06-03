import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class AIEmbedding(Base):
    """Per-user vehicle RAG embeddings."""
    __tablename__ = "ai_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    chunk_type = Column(Text, nullable=False)  # trip_summary | charging_event | vehicle_stats | location
    chunk_text = Column(Text, nullable=False)
    embedding = Column(Text, nullable=False)  # stored as JSON string (pgvector vector)
    metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(TIMESTAMPTZ, default=datetime.utcnow)
    updated_at = Column(TIMESTAMPTZ, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ai_embeddings_user_vehicle_idx", "user_id", "vehicle_id"),
        Index("ai_embeddings_user_type_created_idx", "user_id", "chunk_type", "created_at"),
        UniqueConstraint("user_id", "vehicle_id", "chunk_type", name="uq_ai_emb_source"),
        Index("ai_embeddings_source_unique_idx", "user_id", "vehicle_id", "chunk_type", postgresql_using="btree",
              postgresql_ops={"user_id": "btree", "vehicle_id": "btree", "chunk_type": "btree"}),
    )


class AIEmbeddingsQueue(Base):
    """Async ingestion queue."""
    __tablename__ = "ai_embeddings_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    chunk_type = Column(Text, nullable=False)
    source_id = Column(Text, nullable=False)
    status = Column(Text, default="pending")  # pending | processing | done | failed
    retry_count = Column(UUID(as_uuid=True), default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMPTZ, default=datetime.utcnow)
    processed_at = Column(TIMESTAMPTZ, nullable=True)


class AIChatSession(Base):
    """Chat session (session-scoped, not persistent for privacy)."""
    __tablename__ = "ai_chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=True)
    provider = Column(Text, default="minimax")
    created_at = Column(TIMESTAMPTZ, default=datetime.utcnow)
    last_message_at = Column(TIMESTAMPTZ, default=datetime.utcnow)


class AIChatMessage(Base):
    """Chat message within a session."""
    __tablename__ = "ai_chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    role = Column(Text, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    sources = Column(JSONB, default=list)
    created_at = Column(TIMESTAMPTZ, default=datetime.utcnow)