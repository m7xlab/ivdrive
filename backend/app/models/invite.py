import uuid
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid

class InviteRequest(Base):
    __tablename__ = "invite_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, approved, rejected, used
    token: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
