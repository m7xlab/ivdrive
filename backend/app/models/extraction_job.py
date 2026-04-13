import uuid
import enum
from datetime import datetime
from sqlalchemy import DateTime, Enum, ForeignKey, String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, generate_uuid

class ExtractionJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class ExtractionJob(TimestampMixin, Base):
    __tablename__ = "extraction_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    status: Mapped[ExtractionJobStatus] = mapped_column(Enum(ExtractionJobStatus), default=ExtractionJobStatus.PENDING, nullable=False)
    file_url: Mapped[str | None] = mapped_column(String, nullable=True)
    password: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    user = relationship("User", back_populates="extraction_jobs")
