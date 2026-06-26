"""
Push endpoints — called by EBP dev code in real time.

Single entry:
    POST /api/log
    Header: X-API-Key: llk_xxx
    Body: { api_code, level, message, logged_at?, run_id? }

Batch (multiple entries at once):
    POST /api/logs/batch
    Header: X-API-Key: llk_xxx
    Body: { entries: [...], run_id? }

Levels: info | warning | error | system
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import hash_api_key
from app.models.api_key import ApiKey
from app.models.log_entry import LogEntry
from app.models.log_session import LogSession

router = APIRouter(tags=["push"])

Level = Literal["info", "warning", "error", "system"]


# ─── Auth helper ─────────────────────────────────────────────────────────────

async def _get_api_key(raw_key: str, db: AsyncSession) -> ApiKey:
    key_hash = hash_api_key(raw_key)
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clé API invalide")
    api_key.last_used_at = datetime.now(timezone.utc)
    return api_key


# ─── Session helper ───────────────────────────────────────────────────────────

async def _get_or_create_session(
    client_id: UUID,
    run_id: str | None,
    db: AsyncSession,
) -> LogSession:
    """
    If run_id is provided, reuse or create the LogSession for that run.
    If no run_id, create a fresh session.
    """
    if run_id:
        result = await db.execute(
            select(LogSession).where(
                LogSession.client_id == client_id,
                LogSession.run_id == run_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    session = LogSession(
        client_id=client_id,
        run_id=run_id,
    )
    db.add(session)
    await db.flush()
    return session


# ─── Schemas ──────────────────────────────────────────────────────────────────

class LogEntryIn(BaseModel):
    api_code: str
    level: Level = "info"
    message: str
    logged_at: datetime | None = None
    run_id: str | None = None


class BatchIn(BaseModel):
    entries: list[LogEntryIn]
    # run_id at batch level applies to all entries that don't set their own
    run_id: str | None = None


class PushResponse(BaseModel):
    id: str
    received_at: str


class BatchResponse(BaseModel):
    count: int
    received_at: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/log", response_model=PushResponse, status_code=201)
@limiter.limit("60/minute")
async def push_log(
    request: Request,
    body: LogEntryIn,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Push a single log entry from EBP dev code."""
    api_key = await _get_api_key(x_api_key, db)

    logged_at = body.logged_at or datetime.now(timezone.utc)
    if logged_at.tzinfo is None:
        logged_at = logged_at.replace(tzinfo=timezone.utc)

    session = await _get_or_create_session(api_key.client_id, body.run_id, db)

    entry = LogEntry(
        session_id=session.id,
        client_id=api_key.client_id,
        api_code=body.api_code,
        logged_at=logged_at,
        level=body.level,
        message=body.message,
        raw_line=f"API {body.api_code} - {logged_at.strftime('%d/%m/%Y %H:%M:%S')} : {body.level} : {body.message}",
    )
    db.add(entry)

    # Update session counters
    session.entry_count = (session.entry_count or 0) + 1
    if body.level == "error":
        session.error_count = (session.error_count or 0) + 1
    elif body.level == "warning":
        session.warning_count = (session.warning_count or 0) + 1

    await db.commit()
    await db.refresh(entry)

    return PushResponse(id=str(entry.id), received_at=entry.logged_at.isoformat())


@router.post("/logs/batch", response_model=BatchResponse, status_code=201)
@limiter.limit("30/minute")
async def push_logs_batch(
    request: Request,
    body: BatchIn,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Push multiple log entries in one call (useful to flush a buffer)."""
    if not body.entries:
        return BatchResponse(count=0, received_at=datetime.now(timezone.utc).isoformat())

    api_key = await _get_api_key(x_api_key, db)

    # Group entries by run_id to minimise session lookups
    sessions: dict[str | None, LogSession] = {}

    entries_to_insert = []
    error_count = 0
    warning_count = 0

    for item in body.entries:
        run_id = item.run_id or body.run_id
        if run_id not in sessions:
            sessions[run_id] = await _get_or_create_session(api_key.client_id, run_id, db)
        session = sessions[run_id]

        logged_at = item.logged_at or datetime.now(timezone.utc)
        if logged_at.tzinfo is None:
            logged_at = logged_at.replace(tzinfo=timezone.utc)

        entries_to_insert.append(LogEntry(
            session_id=session.id,
            client_id=api_key.client_id,
            api_code=item.api_code,
            logged_at=logged_at,
            level=item.level,
            message=item.message,
            raw_line=f"API {item.api_code} - {logged_at.strftime('%d/%m/%Y %H:%M:%S')} : {item.level} : {item.message}",
        ))

        if item.level == "error":
            error_count += 1
        elif item.level == "warning":
            warning_count += 1

    db.add_all(entries_to_insert)

    # Update all session counters
    for session in sessions.values():
        session.entry_count = (session.entry_count or 0) + len(body.entries)
        session.error_count = (session.error_count or 0) + error_count
        session.warning_count = (session.warning_count or 0) + warning_count

    await db.commit()

    return BatchResponse(
        count=len(entries_to_insert),
        received_at=datetime.now(timezone.utc).isoformat(),
    )
