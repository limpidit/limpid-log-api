"""
Endpoint to receive log files from EBP installations.
Authentication: X-API-Key header.
Supports:
  - multipart/form-data with a 'file' field
  - raw text body (Content-Type: text/plain)
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_api_key
from app.models.api_key import ApiKey
from app.models.client import Client
from app.models.log_entry import LogEntry
from app.models.log_session import LogSession
from app.services.log_parser import extract_batch_uuid_from_filename, parse_log_file

router = APIRouter(prefix="/push", tags=["push"])


async def _resolve_api_key(x_api_key: str, db: AsyncSession) -> ApiKey:
    key_hash = hash_api_key(x_api_key)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clé API invalide")
    api_key.last_used_at = datetime.now(timezone.utc)
    return api_key


async def _process_log(
    content: str,
    filename: str | None,
    api_key: ApiKey,
    db: AsyncSession,
) -> dict:
    # Parse
    parsed = parse_log_file(content, filename)

    # Get or create client
    result = await db.execute(select(Client).where(Client.id == api_key.client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=500, detail="Client introuvable pour cette clé API")

    # Update client db_id if we got it from logs
    if parsed.db_id and not client.db_id:
        client.db_id = parsed.db_id
    if parsed.api_names:
        pass  # stored per entry

    # Create session
    batch_uuid = extract_batch_uuid_from_filename(filename) if filename else None
    session = LogSession(
        client_id=client.id,
        filename=filename,
        batch_uuid=batch_uuid,
        received_at=datetime.now(timezone.utc),
        entry_count=len(parsed.lines),
        error_count=sum(1 for l in parsed.lines if l.level == "error"),
        warning_count=sum(1 for l in parsed.lines if l.level == "warning"),
    )
    db.add(session)
    await db.flush()

    # Insert entries in bulk
    entries = []
    for pl in parsed.lines:
        entries.append(LogEntry(
            session_id=session.id,
            client_id=client.id,
            api_code=pl.api_code,
            api_name=parsed.api_names.get(pl.api_code),
            logged_at=pl.logged_at,
            level=pl.level,
            message=pl.message,
            raw_line=pl.raw_line,
        ))

    db.add_all(entries)
    await db.commit()

    return {
        "session_id": str(session.id),
        "client": client.db_name,
        "entry_count": session.entry_count,
        "error_count": session.error_count,
        "warning_count": session.warning_count,
    }


@router.post("/logs")
async def push_logs_multipart(
    file: UploadFile = File(...),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Receive a log file as multipart upload."""
    api_key = await _resolve_api_key(x_api_key, db)

    raw = await file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")

    return await _process_log(content, file.filename, api_key, db)


@router.post("/logs/raw")
async def push_logs_raw(
    request: Request,
    filename: str | None = None,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Receive log content as raw text body."""
    api_key = await _resolve_api_key(x_api_key, db)

    raw = await request.body()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")

    return await _process_log(content, filename, api_key, db)
