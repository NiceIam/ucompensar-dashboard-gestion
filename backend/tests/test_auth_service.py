"""Unit tests for auth_service.py — PI0320251.

Tests:
- update_user_profile whitelist enforcement
- update_user_profile SQL SET clause safety
- register_organization atomic rollback when create_org_database fails
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_PORT", "5432")
os.environ.setdefault("DATABASE_USER", "postgres")
os.environ.setdefault("DATABASE_PASSWORD", "postgres")
os.environ.setdefault("DATABASE_NAME", "pi_main")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-api-key")
os.environ.setdefault("APP_SECRET_KEY", "test-app-secret-key-at-least-32-chars-ok")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("BCRYPT_ROUNDS", "10")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool_conn(conn: AsyncMock) -> MagicMock:
    """Wrap a mock connection in a mock pool whose acquire() is a context manager."""
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


# ---------------------------------------------------------------------------
# update_user_profile — whitelist enforcement
# ---------------------------------------------------------------------------

class TestUpdateUserProfileWhitelist:
    """update_user_profile must reject fields outside ALLOWED_PROFILE_FIELDS."""

    @pytest.mark.asyncio
    async def test_update_user_profile_rechaza_campo_no_permitido(self):
        """Passing is_admin=True via model_dump must raise HTTP 422.

        Pydantic v2 does not allow patching instance methods directly, so we
        patch the class method for the duration of this test.
        """
        from fastapi import HTTPException
        from app.models.schemas import ProfileUpdateRequest
        from app.services import auth_service

        body = ProfileUpdateRequest(full_name="Legit Name")
        # Patch model_dump on the class temporarily — Pydantic v2 compatible
        original = ProfileUpdateRequest.model_dump

        def _injected_dump(self, **kwargs):
            return {"is_admin": True, "full_name": "Legit Name"}

        ProfileUpdateRequest.model_dump = _injected_dump  # type: ignore[method-assign]
        try:
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.update_user_profile(
                    user_id="user-uuid",
                    org_id="org-uuid",
                    body=body,
                )
        finally:
            ProfileUpdateRequest.model_dump = original  # type: ignore[method-assign]

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_update_user_profile_acepta_campos_whitelist(self):
        """full_name, phone, avatar_url, preferences must pass validation and call DB."""
        from app.models.schemas import ProfileUpdateRequest, UserProfileResponse
        from app.services import auth_service
        import datetime

        body = ProfileUpdateRequest(
            full_name="Ana García",
            phone="+57 300 123 4567",
            avatar_url="https://cdn.example.com/avatar.png",
            preferences={"theme": "dark"},
        )

        fake_row = {
            "id": "user-uuid",
            "email": "ana@example.com",
            "full_name": "Ana García",
            "org_id": "org-uuid",
            "role": "owner",
            "avatar_url": "https://cdn.example.com/avatar.png",
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=fake_row)
        pool = _make_pool_conn(conn)

        with patch("app.services.auth_service.get_main_pool", AsyncMock(return_value=pool)):
            result = await auth_service.update_user_profile(
                user_id="user-uuid",
                org_id="org-uuid",
                body=body,
            )

        assert isinstance(result, UserProfileResponse)
        assert result.full_name == "Ana García"

    @pytest.mark.asyncio
    async def test_update_user_profile_rechaza_role(self):
        """Passing role via model_dump injection must raise HTTP 422."""
        from fastapi import HTTPException
        from app.models.schemas import ProfileUpdateRequest
        from app.services import auth_service

        body = ProfileUpdateRequest(full_name="Legit")
        original = ProfileUpdateRequest.model_dump

        def _inject(self, **kwargs):
            return {"role": "admin", "full_name": "Legit"}

        ProfileUpdateRequest.model_dump = _inject  # type: ignore[method-assign]
        try:
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.update_user_profile("uid", "oid", body)
        finally:
            ProfileUpdateRequest.model_dump = original  # type: ignore[method-assign]

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_update_user_profile_rechaza_email(self):
        """Passing email via model_dump injection must raise HTTP 422."""
        from fastapi import HTTPException
        from app.models.schemas import ProfileUpdateRequest
        from app.services import auth_service

        body = ProfileUpdateRequest(full_name="Legit")
        original = ProfileUpdateRequest.model_dump

        def _inject(self, **kwargs):
            return {"email": "hacker@evil.com", "full_name": "Legit"}

        ProfileUpdateRequest.model_dump = _inject  # type: ignore[method-assign]
        try:
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.update_user_profile("uid", "oid", body)
        finally:
            ProfileUpdateRequest.model_dump = original  # type: ignore[method-assign]

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_update_user_profile_rechaza_password_hash(self):
        """Passing password_hash via model_dump injection must raise HTTP 422."""
        from fastapi import HTTPException
        from app.models.schemas import ProfileUpdateRequest
        from app.services import auth_service

        body = ProfileUpdateRequest(full_name="Legit")
        original = ProfileUpdateRequest.model_dump

        def _inject(self, **kwargs):
            return {"password_hash": "$2b$10$fakehash", "full_name": "Legit"}

        ProfileUpdateRequest.model_dump = _inject  # type: ignore[method-assign]
        try:
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.update_user_profile("uid", "oid", body)
        finally:
            ProfileUpdateRequest.model_dump = original  # type: ignore[method-assign]

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_update_user_profile_rechaza_deleted_at(self):
        """Passing deleted_at via model_dump injection must raise HTTP 422."""
        from fastapi import HTTPException
        from app.models.schemas import ProfileUpdateRequest
        from app.services import auth_service
        import datetime

        body = ProfileUpdateRequest(full_name="Legit")
        original = ProfileUpdateRequest.model_dump

        def _inject(self, **kwargs):
            return {"deleted_at": datetime.datetime.now().isoformat(), "full_name": "Legit"}

        ProfileUpdateRequest.model_dump = _inject  # type: ignore[method-assign]
        try:
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.update_user_profile("uid", "oid", body)
        finally:
            ProfileUpdateRequest.model_dump = original  # type: ignore[method-assign]

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_update_user_profile_rechaza_org_id(self):
        """Passing org_id via model_dump injection must raise HTTP 422."""
        from fastapi import HTTPException
        from app.models.schemas import ProfileUpdateRequest
        from app.services import auth_service

        body = ProfileUpdateRequest(full_name="Legit")
        original = ProfileUpdateRequest.model_dump

        def _inject(self, **kwargs):
            return {"org_id": "other-org-uuid", "full_name": "Legit"}

        ProfileUpdateRequest.model_dump = _inject  # type: ignore[method-assign]
        try:
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.update_user_profile("uid", "oid", body)
        finally:
            ProfileUpdateRequest.model_dump = original  # type: ignore[method-assign]

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_update_user_profile_query_usa_solo_columnas_validas(self):
        """SQL SET clause must NOT contain any field outside the whitelist."""
        from app.models.schemas import ProfileUpdateRequest
        from app.services import auth_service
        import datetime

        body = ProfileUpdateRequest(full_name="Carlos Pérez", phone="123456789")

        captured_sql: list[str] = []

        async def _capture_fetchrow(sql: str, *args, **kwargs):
            captured_sql.append(sql)
            return {
                "id": "user-uuid",
                "email": "carlos@example.com",
                "full_name": "Carlos Pérez",
                "org_id": "org-uuid",
                "role": "owner",
                "avatar_url": None,
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }

        conn = AsyncMock()
        conn.fetchrow = _capture_fetchrow
        pool = _make_pool_conn(conn)

        with patch("app.services.auth_service.get_main_pool", AsyncMock(return_value=pool)):
            await auth_service.update_user_profile(
                user_id="user-uuid",
                org_id="org-uuid",
                body=body,
            )

        assert len(captured_sql) == 1
        sql = captured_sql[0].lower()

        # Extract only the SET clause (before RETURNING) to avoid false
        # positives from the RETURNING column list which legitimately contains
        # `email`, `role`, etc. for reading back the updated row.
        set_section = sql.split("returning")[0]

        disallowed_set_columns = {"is_admin", "password_hash", "deleted_at"}
        for col in disallowed_set_columns:
            assert col not in set_section, (
                f"Disallowed column '{col}' found in SET clause: {set_section}"
            )
        # email and role must NOT appear in the SET assignments
        # They can appear in RETURNING but never in SET.
        for forbidden_in_set in ("email =", "role ="):
            assert forbidden_in_set not in set_section, (
                f"'{forbidden_in_set}' must not appear in SET clause: {set_section}"
            )
        # Permitted columns must be present in the SET clause
        assert "full_name" in set_section
        assert "phone" in set_section


# ---------------------------------------------------------------------------
# register_organization — atomic rollback
# ---------------------------------------------------------------------------

class TestRegisterOrganizationRollback:
    """If create_org_database raises, org+user rows must be deleted."""

    @pytest.mark.asyncio
    async def test_register_atomic_rollback_when_create_org_database_fails(self):
        """On create_org_database failure, org and user must be deleted and HTTP 500 raised."""
        from fastapi import HTTPException
        from app.models.schemas import UserRegister
        from app.services import auth_service

        body = UserRegister(
            email="nuevo@ejemplo.com",
            password="SuperSecret123!",
            full_name="Nuevo Usuario",
            org_name="Mi Empresa S.A.S",
            sector="comercio",
            size="pequeña",
            city="Bogotá",
        )

        org_row = {"id": "org-uuid-1234", "name": "Mi Empresa S.A.S"}
        user_row = {"id": "user-uuid-5678", "email": body.email}

        conn = AsyncMock()
        # First fetchrow → org creation
        # Second fetchval → email uniqueness check (None = not existing)
        # Third fetchrow → user creation
        conn.fetchrow = AsyncMock(side_effect=[org_row, user_row])
        conn.fetchval = AsyncMock(return_value=None)
        conn.execute = AsyncMock()

        pool = _make_pool_conn(conn)

        with patch("app.services.auth_service.get_main_pool", AsyncMock(return_value=pool)):
            with patch(
                "app.services.auth_service.create_org_database",
                AsyncMock(side_effect=Exception("DB creation failed")),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await auth_service.register_organization(body)

        assert exc_info.value.status_code == 500
        # Verify cleanup: execute was called to delete user and org
        execute_calls = [str(call) for call in conn.execute.call_args_list]
        assert any("DELETE" in c.upper() for c in execute_calls), (
            "Expected DELETE statements during rollback"
        )
