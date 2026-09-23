"""Unit tests for dashboard_script_service._script_path — PI0320251.

_script_path must:
- Accept valid UUIDs and return a path under SCRIPTS_DIR/<org_id>/<dashboard_id>.py
- Raise ValueError for any non-UUID org_id or dashboard_id (path traversal prevention)
"""

import os

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

VALID_ORG_UUID = "550e8400-e29b-41d4-a716-446655440000"
VALID_DASH_UUID = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


class TestScriptPathValidation:
    """_script_path enforces UUID-only inputs to prevent directory traversal."""

    def test_script_path_rechaza_org_id_no_uuid(self):
        """Non-UUID org_id (path traversal attempt) must raise ValueError."""
        from app.services.dashboard_script_service import _script_path

        with pytest.raises(ValueError):
            _script_path("../../etc", VALID_DASH_UUID)

    def test_script_path_rechaza_dashboard_id_no_uuid(self):
        """Non-UUID dashboard_id (path traversal attempt) must raise ValueError."""
        from app.services.dashboard_script_service import _script_path

        with pytest.raises(ValueError):
            _script_path(VALID_ORG_UUID, "../../passwd")

    def test_script_path_rechaza_ambos_ids_invalidos(self):
        """Both IDs being invalid must raise ValueError."""
        from app.services.dashboard_script_service import _script_path

        with pytest.raises(ValueError):
            _script_path("not-a-uuid", "also-not-a-uuid")

    def test_script_path_rechaza_cadena_vacia_org_id(self):
        """Empty string org_id must raise ValueError."""
        from app.services.dashboard_script_service import _script_path

        with pytest.raises(ValueError):
            _script_path("", VALID_DASH_UUID)

    def test_script_path_rechaza_cadena_vacia_dashboard_id(self):
        """Empty string dashboard_id must raise ValueError."""
        from app.services.dashboard_script_service import _script_path

        with pytest.raises(ValueError):
            _script_path(VALID_ORG_UUID, "")

    def test_script_path_rechaza_none_como_org_id(self):
        """None org_id must raise ValueError (not TypeError leaking)."""
        from app.services.dashboard_script_service import _script_path

        with pytest.raises((ValueError, TypeError)):
            _script_path(None, VALID_DASH_UUID)  # type: ignore[arg-type]

    def test_script_path_acepta_uuids_validos(self):
        """Valid UUIDs must return a path under SCRIPTS_DIR/<org>/<dash>.py."""
        from app.services.dashboard_script_service import _script_path, SCRIPTS_DIR

        path = _script_path(VALID_ORG_UUID, VALID_DASH_UUID)

        assert path.endswith(f"{VALID_DASH_UUID}.py")
        assert VALID_ORG_UUID in path
        assert path.startswith(SCRIPTS_DIR)

    def test_script_path_no_contiene_traversal_en_resultado(self):
        """The resolved path must not contain .. segments."""
        from app.services.dashboard_script_service import _script_path

        path = _script_path(VALID_ORG_UUID, VALID_DASH_UUID)
        normalized = os.path.normpath(path)

        assert ".." not in normalized.split(os.sep)

    def test_script_path_extension_py(self):
        """Output path must have .py extension."""
        from app.services.dashboard_script_service import _script_path

        path = _script_path(VALID_ORG_UUID, VALID_DASH_UUID)

        assert path.endswith(".py")
