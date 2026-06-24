from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.client import Client
from app.models.log_entry import LogEntry
from app.models.log_session import LogSession
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardStats(BaseModel):
    clients_count: int
    logs_today: int
    logs_24h: int
    errors_today: int
    warnings_today: int
    sessions_today: int
    recent_errors: list[dict]


@router.get("", response_model=DashboardStats)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since_24h = now - timedelta(hours=24)

    clients_count = (await db.execute(select(func.count(Client.id)))).scalar_one()

    logs_today = (await db.execute(
        select(func.count(LogEntry.id)).where(LogEntry.logged_at >= today)
    )).scalar_one()

    logs_24h = (await db.execute(
        select(func.count(LogEntry.id)).where(LogEntry.logged_at >= since_24h)
    )).scalar_one()

    errors_today = (await db.execute(
        select(func.count(LogEntry.id)).where(LogEntry.logged_at >= today, LogEntry.level == "error")
    )).scalar_one()

    warnings_today = (await db.execute(
        select(func.count(LogEntry.id)).where(LogEntry.logged_at >= today, LogEntry.level == "warning")
    )).scalar_one()

    sessions_today = (await db.execute(
        select(func.count(LogSession.id)).where(LogSession.started_at >= today)
    )).scalar_one()

    # Last 10 errors (most recent, with client name)
    recent_errors_q = (
        select(LogEntry, Client.db_name, Client.display_name)
        .join(Client, LogEntry.client_id == Client.id)
        .where(LogEntry.level == "error")
        .order_by(LogEntry.logged_at.desc())
        .limit(10)
    )
    rows = (await db.execute(recent_errors_q)).all()
    recent_errors = [
        {
            "id": str(row.LogEntry.id),
            "client": row.display_name or row.db_name,
            "api_code": row.LogEntry.api_code,
            "message": row.LogEntry.message,
            "logged_at": row.LogEntry.logged_at.isoformat(),
        }
        for row in rows
    ]

    return DashboardStats(
        clients_count=clients_count,
        logs_today=logs_today,
        logs_24h=logs_24h,
        errors_today=errors_today,
        warnings_today=warnings_today,
        sessions_today=sessions_today,
        recent_errors=recent_errors,
    )
