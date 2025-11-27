"""
Janua Authentication Integration for Galvana/Electrochem-Sim

Provides JWT verification using Janua (MADFAM's centralized auth service).
Can work alongside the existing local auth for backward compatibility.
"""

import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

load_dotenv()

# Janua configuration
JANUA_API_URL = os.getenv("JANUA_API_URL", "http://localhost:8000/api/v1")
JANUA_JWT_SECRET = os.getenv("JANUA_JWT_SECRET", "dev-shared-janua-secret-32chars")
JANUA_JWT_ALGORITHM = os.getenv("JANUA_JWT_ALGORITHM", "HS256")
JANUA_AUTH_ENABLED = os.getenv("JANUA_AUTH_ENABLED", "true").lower() == "true"

# Security scheme for JWT Bearer tokens
janua_security = HTTPBearer(auto_error=False)


class JanuaUser(BaseModel):
    """Authenticated user from Janua JWT."""

    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    roles: list[str] = []
    permissions: list[str] = []
    org_id: Optional[str] = None


class JanuaTokenPayload(BaseModel):
    """JWT token payload structure from Janua."""

    sub: str  # User ID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    roles: list[str] = []
    permissions: list[str] = []
    org_id: Optional[str] = None
    exp: int
    iat: int
    iss: str = "janua"


def verify_janua_token(token: str) -> Optional[JanuaTokenPayload]:
    """
    Verify a Janua JWT token.

    Args:
        token: JWT access token from Janua

    Returns:
        JanuaTokenPayload if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token,
            JANUA_JWT_SECRET,
            algorithms=[JANUA_JWT_ALGORITHM],
            options={"verify_exp": True},
        )

        return JanuaTokenPayload(
            sub=payload.get("sub"),
            email=payload.get("email"),
            first_name=payload.get("first_name"),
            last_name=payload.get("last_name"),
            roles=payload.get("roles", []),
            permissions=payload.get("permissions", []),
            org_id=payload.get("org_id"),
            exp=payload.get("exp"),
            iat=payload.get("iat"),
            iss=payload.get("iss", "janua"),
        )
    except JWTError as e:
        return None


async def get_janua_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(janua_security),
) -> JanuaUser:
    """
    FastAPI dependency to get current authenticated user from Janua.

    Raises HTTPException 401 if not authenticated.
    """
    if not JANUA_AUTH_ENABLED:
        # Return a mock user for development when Janua auth is disabled
        return JanuaUser(
            id="dev-user",
            email="dev@galvana.com",
            first_name="Dev",
            last_name="User",
            full_name="Dev User",
            roles=["user"],
            permissions=["read", "write", "simulate"],
        )

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_payload = verify_janua_token(credentials.credentials)

    if not token_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    full_name = None
    if token_payload.first_name and token_payload.last_name:
        full_name = f"{token_payload.first_name} {token_payload.last_name}"
    elif token_payload.first_name:
        full_name = token_payload.first_name

    return JanuaUser(
        id=token_payload.sub,
        email=token_payload.email,
        first_name=token_payload.first_name,
        last_name=token_payload.last_name,
        full_name=full_name,
        roles=token_payload.roles,
        permissions=token_payload.permissions,
        org_id=token_payload.org_id,
    )


async def get_janua_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(janua_security),
) -> Optional[JanuaUser]:
    """
    FastAPI dependency to get current user if authenticated via Janua.

    Returns None if not authenticated (doesn't raise exception).
    """
    if not credentials:
        return None

    token_payload = verify_janua_token(credentials.credentials)

    if not token_payload:
        return None

    full_name = None
    if token_payload.first_name and token_payload.last_name:
        full_name = f"{token_payload.first_name} {token_payload.last_name}"
    elif token_payload.first_name:
        full_name = token_payload.first_name

    return JanuaUser(
        id=token_payload.sub,
        email=token_payload.email,
        first_name=token_payload.first_name,
        last_name=token_payload.last_name,
        full_name=full_name,
        roles=token_payload.roles,
        permissions=token_payload.permissions,
        org_id=token_payload.org_id,
    )


def require_janua_role(required_role: str):
    """
    Dependency factory for role-based access control with Janua.

    Usage:
        @router.get("/admin")
        async def admin_endpoint(user: JanuaUser = Depends(require_janua_role("admin"))):
            ...
    """

    async def role_checker(user: JanuaUser = Depends(get_janua_user)) -> JanuaUser:
        if required_role not in user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required",
            )
        return user

    return role_checker


def require_janua_permission(required_permission: str):
    """
    Dependency factory for permission-based access control with Janua.

    Usage:
        @router.post("/simulate")
        async def run_simulation(user: JanuaUser = Depends(require_janua_permission("simulate"))):
            ...
    """

    async def permission_checker(
        user: JanuaUser = Depends(get_janua_user),
    ) -> JanuaUser:
        if required_permission not in user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{required_permission}' required",
            )
        return user

    return permission_checker


# Convenience dependencies
require_janua_user = Depends(get_janua_user)
require_janua_admin = Depends(require_janua_role("admin"))
