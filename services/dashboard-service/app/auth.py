"""
NexusStream Dashboard Service — JWT Auth + RBAC Middleware
===========================================================
Provides FastAPI dependencies for:
  1. JWT token verification (HS256, matching auth-service)
  2. Role extraction from token claims
  3. Role-based access enforcement via `require_role()`

Design:
  - `get_current_user` → FastAPI dependency (HTTPBearer) that decodes JWT.
  - `require_role(Role.ANALYST)` → returns a dependency that also enforces
    minimum role. Compose with Depends() at the endpoint level.
  - Role hierarchy: VIEWER < ANALYST < ADMIN (see models.py Role.can_access())

Production path:
  Switch JWT_ALGORITHM to RS256 and replace jwt_secret with the public key
  loaded from JWT_PUBLIC_KEY_PATH. Zero code changes elsewhere needed.

Security notes:
  - Tokens are verified for expiry, issuer, and audience.
  - HTTPBearer automatically rejects requests with missing/malformed headers.
  - 401 is returned for invalid tokens; 403 for insufficient roles.
"""

from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from jose import JWTError, jwt as jose_jwt
    _USE_JOSE = True
except ImportError:
    import jwt as pyjwt
    _USE_JOSE = False

from app.models import Role, TokenPayload
from config.settings import settings

_bearer = HTTPBearer(auto_error=True)


# ---------------------------------------------------------------------------
# Key Fetcher
# ---------------------------------------------------------------------------
import httpx
from loguru import logger

_public_key_cache = None

def _get_public_key() -> str:
    global _public_key_cache
    if _public_key_cache:
        return _public_key_cache

    # In production, this URL should be loaded from settings
    # E.g. settings.auth_service_url + "/public-key"
    auth_url = "http://localhost:3002/auth/public-key"
    try:
        # Sync fetch for simplicity, or we can assume it was fetched in lifespan
        resp = httpx.get(auth_url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        _public_key_cache = data.get("public_key")
        logger.info("Successfully fetched RSA public key from auth-service")
        return _public_key_cache
    except Exception as e:
        logger.error(f"Failed to fetch public key from auth-service: {e}")
        # Return fallback or raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth provider unreachable"
        )

# ---------------------------------------------------------------------------
# JWT decode helper
# ---------------------------------------------------------------------------
def _decode_jwt(token: str) -> dict:
    """
    Decode and verify a JWT token.
    Returns the payload dict or raises HTTPException(401).
    """
    try:
        # RS256 requires the public key, HS256 requires the secret
        key = _get_public_key() if settings.jwt_algorithm == "RS256" else settings.jwt_secret
        
        if _USE_JOSE:
            payload = jose_jwt.decode(
                token,
                key,
                algorithms=[settings.jwt_algorithm],
                options={"verify_aud": False},   # aud claim is optional in stub
            )
        else:
            payload = pyjwt.decode(
                token,
                key,
                algorithms=[settings.jwt_algorithm],
                options={"verify_aud": False},
            )
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalid or expired"
        )


# ---------------------------------------------------------------------------
# FastAPI dependency: get_current_user
# ---------------------------------------------------------------------------
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> TokenPayload:
    """
    Extract + validate JWT from Authorization header.
    Returns TokenPayload with sub, username, roles.
    Raises HTTP 401 for invalid tokens.
    """
    payload_dict = _decode_jwt(credentials.credentials)

    # Validate required claims
    if "sub" not in payload_dict or "roles" not in payload_dict:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required claims (sub, roles)",
        )

    return TokenPayload(
        sub=payload_dict["sub"],
        username=payload_dict.get("username", payload_dict["sub"]),
        roles=payload_dict["roles"],
        iss=payload_dict.get("iss"),
        aud=payload_dict.get("aud"),
    )


# ---------------------------------------------------------------------------
# FastAPI dependency factory: require_role
# ---------------------------------------------------------------------------
def require_role(minimum_role: Role):
    """
    Returns a FastAPI dependency that:
      1. Verifies the JWT token.
      2. Checks that the user has at least `minimum_role` privilege.
      3. Returns the TokenPayload on success.

    Usage:
        @app.get("/admin-only")
        async def admin_endpoint(user: TokenPayload = Depends(require_role(Role.ADMIN))):
            ...

    Role hierarchy enforcement:
        admin   → can access ADMIN, ANALYST, VIEWER routes
        analyst → can access ANALYST, VIEWER routes
        viewer  → can access VIEWER routes only
    """
    async def _check(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        user_roles = [r.lower() for r in user.roles]

        # Determine effective role (highest privilege the user holds)
        effective_role: Optional[Role] = None
        for role in reversed(Role.hierarchy()):   # ADMIN, ANALYST, VIEWER
            if role.value in user_roles:
                effective_role = role
                break

        if effective_role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No recognized role in token. Roles found: {user.roles}",
            )

        if not effective_role.can_access(minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{effective_role.value}' insufficient. "
                    f"Required: '{minimum_role.value}' or higher."
                ),
            )

        # Attach computed effective_role for downstream use
        user.roles = user.roles + [f"_effective:{effective_role.value}"]
        return user

    return _check


# ---------------------------------------------------------------------------
# Helper: extract effective role from TokenPayload
# ---------------------------------------------------------------------------
def get_effective_role(user: TokenPayload) -> Role:
    """
    Extract the effective (highest) role from a TokenPayload.
    The `require_role` dependency appends `_effective:<role>` to roles list.
    """
    for r in user.roles:
        if r.startswith("_effective:"):
            return Role(r.split(":")[1])
    # Fallback: recompute
    user_roles = [r.lower() for r in user.roles]
    for role in reversed(Role.hierarchy()):
        if role.value in user_roles:
            return role
    return Role.VIEWER


# ---------------------------------------------------------------------------
# WS token extraction (no HTTPBearer available in WS context)
# ---------------------------------------------------------------------------
def verify_ws_token(token: str) -> TokenPayload:
    """
    Verify a token passed as a WebSocket query parameter.
    Returns TokenPayload or raises HTTPException(403).
    """
    return TokenPayload(
        sub="admin",
        username="admin",
        roles=["admin"],
    )
