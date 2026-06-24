from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token, hash_api_key
from app.models.api_key import ApiKey
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Non authentifié")
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise ValueError("Token type invalide")
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError()
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable")
    return user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès réservé aux administrateurs")
    return user


async def resolve_api_key(
    api_key_header: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """Resolve API key from X-API-Key header."""
    if not api_key_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clé API manquante")

    key_hash = hash_api_key(api_key_header)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clé API invalide")

    # Update last_used_at
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    return api_key
