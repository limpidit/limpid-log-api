from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.client import Client
from app.models.log_entry import LogEntry
from app.models.log_session import LogSession
from app.models.user import User

router = APIRouter(prefix="/clients", tags=["clients"])


class ClientStats(BaseModel):
    id: UUID
    db_name: str
    display_name: str | None
    ebp_file: str | None
    db_id: str | None
    created_at: datetime
    session_count: int
    error_count: int
    last_received_at: datetime | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ClientStats])
async def list_clients(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    # Clients with stats
    sessions_subq = (
        select(
            LogSession.client_id,
            func.count(LogSession.id).label("session_count"),
            func.sum(LogSession.error_count).label("error_count"),
            func.max(LogSession.received_at).label("last_received_at"),
        )
        .group_by(LogSession.client_id)
        .subquery()
    )

    q = (
        select(
            Client,
            func.coalesce(sessions_subq.c.session_count, 0).label("session_count"),
            func.coalesce(sessions_subq.c.error_count, 0).label("error_count"),
            sessions_subq.c.last_received_at,
        )
        .outerjoin(sessions_subq, Client.id == sessions_subq.c.client_id)
        .order_by(Client.db_name)
    )

    result = await db.execute(q)
    rows = result.all()

    return [
        ClientStats(
            id=row.Client.id,
            db_name=row.Client.db_name,
            display_name=row.Client.display_name,
            ebp_file=row.Client.ebp_file,
            db_id=row.Client.db_id,
            created_at=row.Client.created_at,
            session_count=row.session_count,
            error_count=row.error_count or 0,
            last_received_at=row.last_received_at,
        )
        for row in rows
    ]
