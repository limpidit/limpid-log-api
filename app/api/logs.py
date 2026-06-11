from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.log_entry import LogEntry
from app.models.log_session import LogSession
from app.models.user import User

router = APIRouter(prefix="/logs", tags=["logs"])


class LogEntryRead(BaseModel):
    id: UUID
    session_id: UUID
    client_id: UUID
    api_code: str
    api_name: str | None
    logged_at: datetime
    level: str
    message: str
    raw_line: str | None

    model_config = {"from_attributes": True}


class LogSessionRead(BaseModel):
    id: UUID
    client_id: UUID
    run_id: str | None
    started_at: datetime
    entry_count: int
    error_count: int
    warning_count: int

    model_config = {"from_attributes": True}


class PaginatedLogs(BaseModel):
    items: list[LogEntryRead]
    total: int
    page: int
    page_size: int


@router.get("", response_model=PaginatedLogs)
async def list_logs(
    client_id: UUID | None = Query(None),
    api_code: str | None = Query(None),
    level: Literal["info", "warning", "error", "system"] | None = Query(None),
    search: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    q = select(LogEntry).order_by(LogEntry.logged_at.desc())

    if client_id:
        q = q.where(LogEntry.client_id == client_id)
    if api_code:
        q = q.where(LogEntry.api_code == api_code)
    if level:
        q = q.where(LogEntry.level == level)
    if search:
        q = q.where(LogEntry.message.ilike(f"%{search}%"))
    if date_from:
        q = q.where(LogEntry.logged_at >= date_from)
    if date_to:
        q = q.where(LogEntry.logged_at <= date_to)

    # Count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Paginate
    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    items = result.scalars().all()

    return PaginatedLogs(items=items, total=total, page=page, page_size=page_size)


@router.get("/sessions", response_model=list[LogSessionRead])
async def list_sessions(
    client_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    q = select(LogSession).order_by(LogSession.started_at.desc()).limit(limit)
    if client_id:
        q = q.where(LogSession.client_id == client_id)
    result = await db.execute(q)
    return result.scalars().all()
