import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LogSession(Base):
    """
    Groups log entries from a single execution run of an EBP API.

    The dev passes a run_id (UUID they generate once at the start of execution).
    All log entries with the same run_id are grouped under the same session.
    If no run_id is provided, each entry gets its own implicit session.
    """
    __tablename__ = "log_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    # Provided by caller to group entries from the same execution
    run_id: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    entry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)

    client: Mapped["Client"] = relationship("Client", back_populates="log_sessions")
    entries: Mapped[list["LogEntry"]] = relationship("LogEntry", back_populates="session", lazy="select")

    __table_args__ = (
        Index("ix_log_sessions_client_run", "client_id", "run_id"),
    )
