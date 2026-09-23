"""Autenticacion JWT local — sin Supabase Auth.

Usa python-jose para firmar/verificar tokens y passlib para hash de passwords.

Seguridad:
- Los tokens se leen EXCLUSIVAMENTE desde cookies HttpOnly (access_token).
- La denylist (_token_denylist) es in-memory con limpieza opportunistic de expirados.
  NOTA: No persiste entre reinicios del servidor. Aceptable para TRL-6/prototipo.
  Plan de migración a Redis para producción antes de TRL-8.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
import bcrypt
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

# Rate limiter instance — shared across the auth router.
# Registered in main.py as app.state.limiter + RateLimitExceeded handler.
limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# JWT Denylist (in-memory)
# ---------------------------------------------------------------------------
# Maps jti → exp datetime. Entries are lazily purged when already-expired.
# WARNING: This dict is NOT shared between workers/processes. For multi-worker
# deployments, migrate to a Redis SET with TTL before going to TRL-8 production.
_token_denylist: dict[str, datetime] = {}


def deny_token(jti: str, exp: datetime) -> None:
    """Añade un jti a la denylist de tokens revocados.

    Realiza limpieza opportunistic de entradas ya expiradas para mantener
    el dict acotado en memoria. In-memory — no persiste entre reinicios.
    """
    now = datetime.now(timezone.utc)
    expired_keys = [k for k, v in _token_denylist.items() if v < now]
    for k in expired_keys:
        del _token_denylist[k]
    _token_denylist[jti] = exp


def is_token_denied(jti: str) -> bool:
    """Verifica si un jti está en la denylist.

    Si la entrada existe pero ya expiró (reloj de la máquina), la elimina
    y devuelve False (el token habría sido rechazado por exp de todas formas).
    """
    if jti not in _token_denylist:
        return False
    if _token_denylist[jti] < datetime.now(timezone.utc):
        del _token_denylist[jti]
        return False
    return True


@dataclass
class CurrentUser:
    user_id: str
    org_id: str
    email: str
    role: str


def hash_password(password: str) -> str:
    settings = get_settings()
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, org_id: str, email: str, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "email": email,
        "role": role,
        "exp": expire,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.APP_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.APP_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    request: Request,
) -> CurrentUser:
    """Valida el JWT y extrae la identidad del usuario.

    Estrategia de lectura de token:
    - Exclusivamente desde cookie HttpOnly `access_token`.
    - El Bearer header ya NO se acepta (M-01 eliminado; ver historial git).
      Los tokens se leen solo de cookies para maximizar la defensa contra XSS.
    """
    settings = get_settings()

    token: Optional[str] = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token,
            settings.APP_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti: str | None = payload.get("jti")
    if jti and is_token_denied(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revocado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str | None = payload.get("sub")
    org_id: str | None = payload.get("org_id")

    if not user_id or not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token incompleto.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        user_id=user_id,
        org_id=org_id,
        email=payload.get("email", ""),
        role=payload.get("role", "viewer"),
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
