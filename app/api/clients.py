from __future__ import annotations

from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.client import Client
from app.models.log_session import LogSession
from app.models.user import User

router = APIRouter(prefix="/clients", tags=["clients"])

# ok | warning | error | silent | unknown
Status = str


def compute_status(
    last_session_at: datetime | None,
    last_session_errors: int,
    last_session_warnings: int,
    expected_log_hours: int,
) -> Status:
    if last_session_at is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    if last_session_at.tzinfo is None:
        last_session_at = last_session_at.replace(tzinfo=timezone.utc)
    age_hours = (now - last_session_at).total_seconds() / 3600
    if age_hours > expected_log_hours:
        return "silent"
    if last_session_errors > 0:
        return "error"
    if last_session_warnings > 0:
        return "warning"
    return "ok"


class ClientStats(BaseModel):
    id: UUID
    db_name: str
    display_name: str | None
    ebp_file: str | None
    db_id: str | None
    expected_log_hours: int
    created_at: datetime
    # Agrégats globaux
    session_count: int
    total_error_count: int
    # Dernière session
    last_session_at: datetime | None
    last_session_errors: int
    last_session_warnings: int
    # Statut calculé : ok | warning | error | silent | unknown
    status: Status

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ClientStats])
async def list_clients(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    global_subq = (
        select(
            LogSession.client_id,
            func.count(LogSession.id).label("session_count"),
            func.coalesce(func.sum(LogSession.error_count), 0).label("total_error_count"),
        )
        .group_by(LogSession.client_id)
        .subquery()
    )

    latest_subq = (
        select(
            LogSession.client_id,
            func.max(LogSession.started_at).label("last_started_at"),
        )
        .group_by(LogSession.client_id)
        .subquery()
    )

    last_session_subq = (
        select(
            LogSession.client_id,
            LogSession.started_at,
            LogSession.error_count.label("last_errors"),
            LogSession.warning_count.label("last_warnings"),
        )
        .join(
            latest_subq,
            (LogSession.client_id == latest_subq.c.client_id) &
            (LogSession.started_at == latest_subq.c.last_started_at),
        )
        .subquery()
    )

    q = (
        select(
            Client,
            func.coalesce(global_subq.c.session_count, 0).label("session_count"),
            func.coalesce(global_subq.c.total_error_count, 0).label("total_error_count"),
            last_session_subq.c.started_at.label("last_session_at"),
            func.coalesce(last_session_subq.c.last_errors, 0).label("last_session_errors"),
            func.coalesce(last_session_subq.c.last_warnings, 0).label("last_session_warnings"),
        )
        .outerjoin(global_subq, Client.id == global_subq.c.client_id)
        .outerjoin(last_session_subq, Client.id == last_session_subq.c.client_id)
        .order_by(last_session_subq.c.started_at.desc().nulls_last())
    )

    rows = (await db.execute(q)).all()

    return [
        ClientStats(
            id=row.Client.id,
            db_name=row.Client.db_name,
            display_name=row.Client.display_name,
            ebp_file=row.Client.ebp_file,
            db_id=row.Client.db_id,
            expected_log_hours=row.Client.expected_log_hours,
            created_at=row.Client.created_at,
            session_count=row.session_count,
            total_error_count=row.total_error_count,
            last_session_at=row.last_session_at,
            last_session_errors=row.last_session_errors,
            last_session_warnings=row.last_session_warnings,
            status=compute_status(
                row.last_session_at,
                row.last_session_errors,
                row.last_session_warnings,
                row.Client.expected_log_hours,
            ),
        )
        for row in rows
    ]
