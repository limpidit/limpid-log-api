import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("log_sessions.id", ondelete="CASCADE"), nullable=False)
    # Denormalized for fast queries
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)

    # From log line
    api_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # Parsed from init line
    api_name: Mapped[str] = mapped_column(String(255), nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # info | warning | error | system
    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_line: Mapped[str] = mapped_column(Text, nullable=True)

    session: Mapped["LogSession"] = relationship("LogSession", back_populates="entries")

    __table_args__ = (
        Index("ix_log_entries_client_logged_at", "client_id", "logged_at"),
    )
