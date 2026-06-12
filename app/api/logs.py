from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, delete, func, select
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


@router.delete("/{log_id}", status_code=204)
async def delete_log(
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(select(LogEntry).where(LogEntry.id == log_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Log introuvable")
    session_id = entry.session_id
    await db.delete(entry)
    await db.commit()
    # Update session counters
    await _refresh_session_counters(db, session_id)


@router.delete("", status_code=200)
async def delete_logs_bulk(
    client_id: UUID | None = Query(None),
    level: Literal["info", "warning", "error", "system"] | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Bulk delete logs. At least one filter required to avoid accidental wipe."""
    if not any([client_id, level, date_from, date_to]):
        raise HTTPException(status_code=400, detail="Au moins un filtre requis")

    q = select(LogEntry.id)
    if client_id:
        q = q.where(LogEntry.client_id == client_id)
    if level:
        q = q.where(LogEntry.level == level)
    if date_from:
        q = q.where(LogEntry.logged_at >= date_from)
    if date_to:
        q = q.where(LogEntry.logged_at <= date_to)

    # Get affected session ids before deletion
    session_q = select(LogEntry.session_id).distinct()
    if client_id:
        session_q = session_q.where(LogEntry.client_id == client_id)
    if level:
        session_q = session_q.where(LogEntry.level == level)
    if date_from:
        session_q = session_q.where(LogEntry.logged_at >= date_from)
    if date_to:
        session_q = session_q.where(LogEntry.logged_at <= date_to)
    session_ids = (await db.execute(session_q)).scalars().all()

    del_q = delete(LogEntry)
    if client_id:
        del_q = del_q.where(LogEntry.client_id == client_id)
    if level:
        del_q = del_q.where(LogEntry.level == level)
    if date_from:
        del_q = del_q.where(LogEntry.logged_at >= date_from)
    if date_to:
        del_q = del_q.where(LogEntry.logged_at <= date_to)

    result = await db.execute(del_q)
    deleted_count = result.rowcount
    await db.commit()

    for sid in session_ids:
        await _refresh_session_counters(db, sid)

    return {"deleted": deleted_count}


async def _refresh_session_counters(db: AsyncSession, session_id: UUID):
    """Recalculate entry/error/warning counts for a session."""
    counts = (await db.execute(
        select(
            func.count(LogEntry.id).label("total"),
            func.coalesce(func.sum(case((LogEntry.level == "error", 1), else_=0)), 0).label("errors"),
            func.coalesce(func.sum(case((LogEntry.level == "warning", 1), else_=0)), 0).label("warnings"),
        ).where(LogEntry.session_id == session_id)
    )).one()

    result = await db.execute(select(LogSession).where(LogSession.id == session_id))
    session = result.scalar_one_or_none()
    if session:
        session.entry_count = counts.total
        session.error_count = counts.errors
        session.warning_count = counts.warnings
        if counts.total == 0:
            await db.delete(session)
        await db.commit()


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
