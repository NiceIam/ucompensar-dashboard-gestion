"""Unit tests for Pydantic schema validators — PI0320251.

Covers:
- UserRegister.sector accepts every BusinessSector enum value
- UserRegister.sector rejects invalid strings
- UserRegister.size accepts known values
- UserRegister.email rejects non-email strings
- ProfileUpdateRequest accepts an empty (all-None) payload
"""

import os

import pytest
from pydantic import ValidationError

os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_PORT", "5432")
os.environ.setdefault("DATABASE_USER", "postgres")
os.environ.setdefault("DATABASE_PASSWORD", "postgres")
os.environ.setdefault("DATABASE_NAME", "pi_main")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-api-key")
os.environ.setdefault("APP_SECRET_KEY", "test-app-secret-key-at-least-32-chars-ok")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("BCRYPT_ROUNDS", "10")

_BASE_REGISTER = {
    "email": "usuario@ejemplo.com",
    "password": "SecurePass1",
    "full_name": "Juan Pérez",
    "org_name": "Mi Empresa",
    "city": "Bogotá",
}


class TestUserRegisterSector:
    """sector field must accept every BusinessSector value and reject unknowns."""

    def test_user_register_sector_acepta_business_sector_enum(self):
        """Each BusinessSector value must be accepted without ValidationError."""
        from app.constants import BusinessSector
        from app.models.schemas import UserRegister

        for sector_value in BusinessSector:
            data = {**_BASE_REGISTER, "sector": sector_value.value}
            user = UserRegister(**data)
            assert user.sector == sector_value

    def test_user_register_sector_rechaza_valor_invalido(self):
        """An unknown sector string must raise ValidationError."""
        from app.models.schemas import UserRegister

        data = {**_BASE_REGISTER, "sector": "sector_inexistente"}
        with pytest.raises(ValidationError):
            UserRegister(**data)

    def test_user_register_sector_rechaza_sector_vacio(self):
        """Empty string sector must raise ValidationError."""
        from app.models.schemas import UserRegister

        data = {**_BASE_REGISTER, "sector": ""}
        with pytest.raises(ValidationError):
            UserRegister(**data)


class TestUserRegisterSize:
    """size field must accept known values and reject others."""

    @pytest.mark.parametrize("size", ["micro", "pequeña", "mediana"])
    def test_user_register_size_acepta_valores_conocidos(self, size: str):
        """Known size values must pass validation."""
        from app.models.schemas import UserRegister

        data = {**_BASE_REGISTER, "size": size}
        user = UserRegister(**data)
        assert user.size == size

    def test_user_register_size_rechaza_valor_desconocido(self):
        """A value outside OrganizationSize enum must raise ValidationError."""
        from app.models.schemas import UserRegister

        data = {**_BASE_REGISTER, "size": "extragrande"}
        with pytest.raises(ValidationError):
            UserRegister(**data)

    def test_user_register_size_rechaza_valor_vacio(self):
        """Empty string size must raise ValidationError."""
        from app.models.schemas import UserRegister

        data = {**_BASE_REGISTER, "size": ""}
        with pytest.raises(ValidationError):
            UserRegister(**data)


class TestUserRegisterEmail:
    """email field must reject invalid email strings."""

    def test_user_register_email_invalido(self):
        """'no-email' is not a valid email address and must raise ValidationError."""
        from app.models.schemas import UserRegister

        data = {**_BASE_REGISTER, "email": "no-email"}
        with pytest.raises(ValidationError):
            UserRegister(**data)

    def test_user_register_email_invalido_sin_dominio(self):
        """'usuario@' without domain must raise ValidationError."""
        from app.models.schemas import UserRegister

        data = {**_BASE_REGISTER, "email": "usuario@"}
        with pytest.raises(ValidationError):
            UserRegister(**data)

    def test_user_register_email_valido_acepta(self):
        """A well-formed email must pass validation."""
        from app.models.schemas import UserRegister

        data = {**_BASE_REGISTER, "email": "valid@domain.co"}
        user = UserRegister(**data)
        assert "@" in user.email


class TestProfileUpdateRequest:
    """ProfileUpdateRequest must be instantiable with all-None payload."""

    def test_profile_update_request_solo_campos_opcionales(self):
        """Empty dict must produce a valid instance (all fields default to None)."""
        from app.models.schemas import ProfileUpdateRequest

        req = ProfileUpdateRequest()
        assert req.full_name is None
        assert req.phone is None
        assert req.avatar_url is None
        assert req.preferences is None

    def test_profile_update_request_acepta_solo_full_name(self):
        """Only providing full_name must be valid."""
        from app.models.schemas import ProfileUpdateRequest

        req = ProfileUpdateRequest(full_name="Nombre Actualizado")
        assert req.full_name == "Nombre Actualizado"

    def test_profile_update_request_full_name_demasiado_corto(self):
        """full_name shorter than 2 chars must raise ValidationError."""
        from app.models.schemas import ProfileUpdateRequest

        with pytest.raises(ValidationError):
            ProfileUpdateRequest(full_name="A")

    def test_profile_update_request_acepta_preferences_dict(self):
        """preferences dict must be stored as-is."""
        from app.models.schemas import ProfileUpdateRequest

        prefs = {"theme": "dark", "language": "es"}
        req = ProfileUpdateRequest(preferences=prefs)
        assert req.preferences == prefs
