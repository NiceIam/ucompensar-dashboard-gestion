from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response, status
from jose import JWTError, jwt

from app.auth import CurrentUserDep, create_access_token, deny_token, get_settings, is_token_denied, limiter
from app.models.schemas import (
    MessageResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    UserLogin,
    UserProfileResponse,
    UserRegister,
)
from app.services.auth_service import (
    get_detailed_profile,
    get_user_profile,
    login_user,
    register_organization,
    update_user_profile,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

_REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Escribe access_token y refresh_token como cookies HttpOnly en la respuesta."""
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.cookies_secure_effective,
        samesite="strict",
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.cookies_secure_effective,
        samesite="strict",
        max_age=settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60,
        path=_REFRESH_COOKIE_PATH,
    )


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra usuario y crea organización",
)
@limiter.limit("5/minute")
async def register(request: Request, response: Response, body: UserRegister) -> MessageResponse:
    """Crea organización + usuario + DB org de forma atómica. Establece cookies HttpOnly."""
    token_data = await register_organization(body)
    _set_auth_cookies(response, token_data.access_token, token_data.refresh_token)
    return MessageResponse(message="Registro exitoso.")


@router.post(
    "/login",
    response_model=MessageResponse,
    summary="Autenticación con email/contraseña",
)
@limiter.limit("10/minute")
async def login(request: Request, response: Response, body: UserLogin) -> MessageResponse:
    """Autentica usuario. Establece cookies HttpOnly; no retorna tokens en el body."""
    token_data = await login_user(body)
    _set_auth_cookies(response, token_data.access_token, token_data.refresh_token)
    return MessageResponse(message="Autenticación exitosa.")


@router.post("/refresh", response_model=MessageResponse, summary="Rota el refresh token")
@limiter.limit("30/minute")
async def refresh_token(request: Request, response: Response) -> MessageResponse:
    """Lee refresh_token de cookie HttpOnly, valida y emite nuevas cookies."""
    settings = get_settings()

    refresh_tok = request.cookies.get("refresh_token")
    if not refresh_tok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token no encontrado.",
        )

    try:
        payload = jwt.decode(
            refresh_tok,
            settings.APP_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado.",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no es de tipo refresh.",
        )

    old_jti = payload.get("jti")
    if old_jti and is_token_denied(old_jti):
        # Reuso de un refresh token ya rotado/revocado -- posible robo.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revocado.",
        )

    user_id: str = payload.get("sub", "")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
        )

    from app.database import get_main_pool
    pool = await get_main_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, org_id, role FROM users WHERE id = $1",
            user_id,
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado.",
        )

    from app.auth import create_refresh_token
    new_access = create_access_token(
        user_id=str(row["id"]),
        org_id=str(row["org_id"]),
        email=row["email"],
        role=row["role"],
    )
    new_refresh = create_refresh_token(user_id=str(row["id"]))

    # Revocar el refresh token viejo al rotar: si alguien mas lo tenia
    # (robado), no sigue siendo valido los ~7 dias restantes de su vida util.
    old_exp_ts = payload.get("exp")
    if old_jti and old_exp_ts:
        deny_token(old_jti, datetime.fromtimestamp(old_exp_ts, tz=timezone.utc))

    _set_auth_cookies(response, new_access, new_refresh)
    return MessageResponse(message="Token renovado exitosamente.")


@router.post("/logout", response_model=MessageResponse, summary="Cierra sesión")
async def logout(request: Request, response: Response, current_user: CurrentUserDep) -> MessageResponse:
    """Elimina las cookies de autenticación del cliente y revoca los tokens activos.

    Lee los JTIs de access_token y refresh_token ANTES de borrar las cookies,
    luego los añade a la denylist in-memory para que no puedan reutilizarse
    durante el tiempo restante de validez.

    NOTA: La denylist es in-memory y no persiste entre reinicios. Aceptable para
    TRL-6/prototipo. Plan de migración a Redis SET con TTL antes de TRL-8.
    """
    settings = get_settings()

    # Revocar access_token (leer ANTES de borrar la cookie)
    access_tok = request.cookies.get("access_token")
    if access_tok:
        try:
            payload = jwt.decode(
                access_tok,
                settings.APP_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            jti: str | None = payload.get("jti")
            exp_ts = payload.get("exp")
            if jti and exp_ts:
                exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
                deny_token(jti, exp_dt)
        except JWTError:
            pass  # Token ya inválido/expirado — no hay nada que revocar

    # Revocar refresh_token (leer ANTES de borrar la cookie)
    refresh_tok = request.cookies.get("refresh_token")
    if refresh_tok:
        try:
            payload_r = jwt.decode(
                refresh_tok,
                settings.APP_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            jti_r: str | None = payload_r.get("jti")
            exp_ts_r = payload_r.get("exp")
            if jti_r and exp_ts_r:
                exp_dt_r = datetime.fromtimestamp(exp_ts_r, tz=timezone.utc)
                deny_token(jti_r, exp_dt_r)
        except JWTError:
            pass  # Token ya inválido/expirado — no hay nada que revocar

    response.delete_cookie("access_token", path="/", secure=settings.cookies_secure_effective, samesite="strict")
    response.delete_cookie(
        "refresh_token",
        path=_REFRESH_COOKIE_PATH,
        secure=settings.cookies_secure_effective,
        samesite="strict",
    )
    return MessageResponse(message="Sesión cerrada exitosamente.")


@router.get("/me", response_model=UserProfileResponse, summary="Perfil básico del usuario actual")
async def me(current_user: CurrentUserDep) -> UserProfileResponse:
    return await get_user_profile(current_user.user_id, current_user.org_id)


@router.get(
    "/profile",
    response_model=ProfileResponse,
    summary="Perfil detallado con preferencias y datos de la organización",
)
async def get_profile(current_user: CurrentUserDep) -> ProfileResponse:
    return await get_detailed_profile(current_user.user_id, current_user.org_id)


@router.put(
    "/profile",
    response_model=UserProfileResponse,
    summary="Actualiza datos del perfil (no permite cambiar email ni rol)",
)
async def update_profile(
    body: ProfileUpdateRequest,
    current_user: CurrentUserDep,
) -> UserProfileResponse:
    return await update_user_profile(current_user.user_id, current_user.org_id, body)
