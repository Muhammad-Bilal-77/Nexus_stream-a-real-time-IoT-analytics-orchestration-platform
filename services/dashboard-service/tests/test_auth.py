"""
NexusStream Dashboard Service — Auth Unit Tests
===============================================
Run with: pytest tests/test_auth.py -v
"""

import pytest
from fastapi import HTTPException
from app.models import Role, TokenPayload
from app.auth import get_effective_role, require_role, verify_ws_token, _decode_jwt
import jwt as pyjwt
from config.settings import settings


def generate_token(sub: str, roles: list[str]) -> str:
    payload = {"sub": sub, "roles": roles, "username": sub}
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class TestRoles:
    def test_role_hierarchy(self):
        assert Role.ADMIN.can_access(Role.ADMIN) is True
        assert Role.ADMIN.can_access(Role.ANALYST) is True
        assert Role.ADMIN.can_access(Role.VIEWER) is True

        assert Role.ANALYST.can_access(Role.ADMIN) is False
        assert Role.ANALYST.can_access(Role.ANALYST) is True
        assert Role.ANALYST.can_access(Role.VIEWER) is True

        assert Role.VIEWER.can_access(Role.ADMIN) is False
        assert Role.VIEWER.can_access(Role.ANALYST) is False
        assert Role.VIEWER.can_access(Role.VIEWER) is True


class TestAuthMiddleware:
    @pytest.mark.asyncio
    async def test_require_role_success(self):
        user_payload = TokenPayload(sub="test_user", username="test", roles=["viewer", "analyst"])
        
        # Require ANALYST
        dep = require_role(Role.ANALYST)
        
        # Test it passes and returns effectively analyst
        result = await dep(user_payload)
        assert "_effective:analyst" in result.roles
        assert get_effective_role(result) == Role.ANALYST

    @pytest.mark.asyncio
    async def test_require_role_insufficient(self):
        user_payload = TokenPayload(sub="test_user", username="test", roles=["viewer"])
        
        # Require ADMIN
        dep = require_role(Role.ADMIN)
        
        # Test it raises 403
        with pytest.raises(HTTPException) as exc:
            await dep(user_payload)
        
        assert exc.value.status_code == 403
        assert "insufficient" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_require_role_unrecognized(self):
        user_payload = TokenPayload(sub="test_user", username="test", roles=["unknown_role"])
        
        dep = require_role(Role.VIEWER)
        
        with pytest.raises(HTTPException) as exc:
            await dep(user_payload)
        
        assert exc.value.status_code == 403
        assert "No recognized role" in exc.value.detail


class TestTokenParsing:
    def test_ws_token_parsing_valid(self):
        token = generate_token("admin_user", ["admin"])
        payload = verify_ws_token(token)
        assert payload.sub == "admin_user"
        assert payload.username == "admin_user"
        assert "admin" in payload.roles

    def test_ws_token_parsing_invalid(self):
        with pytest.raises(HTTPException) as exc:
            verify_ws_token("invalid.token.here")
        assert exc.value.status_code == 403

    def test_decode_jwt_invalid_signature(self):
        token = pyjwt.encode({"sub": "t"}, "wrong_secret", algorithm="HS256")
        with pytest.raises(HTTPException) as exc:
            _decode_jwt(token)
        assert exc.value.status_code == 401
