"""
Admin endpoints for managing users, clients, and API keys.
All require authentication (any logged-in user for now).
"""

import uuid
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import generate_api_key, hash_api_key, hash_password
from app.models.api_key import ApiKey
from app.models.client import Client
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


# ─── Clients ─────────────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    db_name: str
    display_name: str | None = None
    ebp_file: str | None = None
    sender_email: str | None = None


class ClientRead(BaseModel):
    id: UUID
    db_name: str
    display_name: str | None
    ebp_file: str | None
    db_id: str | None
    sender_email: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/clients", response_model=list[ClientRead])
async def list_clients(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(select(Client).order_by(Client.db_name))
    return result.scalars().all()


@router.post("/clients", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    existing = await db.execute(select(Client).where(Client.db_name == body.db_name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ce client existe déjà")

    client = Client(**body.model_dump())
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return client


@router.put("/clients/{client_id}", response_model=ClientRead)
async def update_client(
    client_id: UUID,
    body: ClientCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable")

    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(client, k, v)
    await db.commit()
    await db.refresh(client)
    return client


# ─── API Keys ─────────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    client_id: UUID
    name: str


class ApiKeyRead(BaseModel):
    id: UUID
    client_id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None
    # key_hash is never exposed

    model_config = {"from_attributes": True}


class ApiKeyCreated(ApiKeyRead):
    # Full key only shown once at creation
    key: str


@router.get("/api-keys", response_model=list[ApiKeyRead])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    return result.scalars().all()


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    # Verify client exists
    result = await db.execute(select(Client).where(Client.id == body.client_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Client introuvable")

    raw_key = generate_api_key()
    api_key = ApiKey(
        client_id=body.client_id,
        name=body.name,
        key_hash=hash_api_key(raw_key),
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyCreated(
        id=api_key.id,
        client_id=api_key.client_id,
        name=api_key.name,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        key=raw_key,
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="Clé API introuvable")
    await db.delete(api_key)
    await db.commit()


# ─── Users ────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str


class UserRead(BaseModel):
    id: UUID
    email: str
    name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/users", response_model=list[UserRead])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(select(User).order_by(User.name))
    return result.scalars().all()


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Cet email existe déjà")

    user = User(
        email=body.email,
        name=body.name,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
