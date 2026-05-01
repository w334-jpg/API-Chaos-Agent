"""JWT authentication utilities.

Provides token creation, verification, and FastAPI dependency injection
for protecting API endpoints. Uses custom AuthenticationError for
consistent error response format across the application.
"""

from __future__ import annotations

import datetime as _dt
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api_chaos_agent.core.config import settings
from api_chaos_agent.core.exceptions import AuthenticationError

_bearer = HTTPBearer(auto_error=False)


def create_access_token(subject: str, expires_delta: _dt.timedelta | None = None) -> str:
    expire = _dt.datetime.now(_dt.timezone.utc) + (
        expires_delta or _dt.timedelta(minutes=settings.auth.access_token_expire_minutes)
    )
    payload = {"sub": subject, "exp": expire, "iat": _dt.datetime.now(_dt.timezone.utc)}
    return jwt.encode(payload, settings.auth.secret_key, algorithm=settings.auth.algorithm)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.auth.secret_key, algorithms=[settings.auth.algorithm])
    except jwt.ExpiredSignatureError:
        raise AuthenticationError(detail="Token expired")
    except jwt.InvalidTokenError:
        raise AuthenticationError(detail="Invalid token")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    if not settings.auth.enabled:
        return {"sub": "anonymous"}
    if credentials is None:
        raise AuthenticationError(detail="Not authenticated")
    return _decode_token(credentials.credentials)


CurrentUser = Annotated[dict, Depends(get_current_user)]
