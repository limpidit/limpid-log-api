import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Short name from log: T2M, FERMATICIDFOUEST, etc.
    db_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    # Display name (can be edited by admin)
    display_name: Mapped[str] = mapped_column(String(255), nullable=True)
    # EBP .ebp file (e.g. T2M.ebp)
    ebp_file: Mapped[str] = mapped_column(String(255), nullable=True)
    # DBId from init log line (per-client UUID in EBP)
    db_id: Mapped[str] = mapped_column(String(100), nullable=True)
    # Email address that sends logs (optional, informational)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="client", lazy="select")
    log_sessions: Mapped[list["LogSession"]] = relationship("LogSession", back_populates="client", lazy="select")
