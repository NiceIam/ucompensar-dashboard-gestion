"""Lógica de negocio de autenticación y gestión de perfiles — PI0320251.

Responsabilidades:
- Registro atómico de organización + usuario + base de datos org
- Login con verificación de password y emisión de tokens JWT
- Obtención y actualización de perfil de usuario
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.database import create_org_database, get_main_pool
from app.models.schemas import (
    ProfileResponse,
    ProfileUpdateRequest,
    TokenResponse,
    UserLogin,
    UserProfileResponse,
    UserRegister,
)

logger = logging.getLogger(__name__)


async def register_organization(body: UserRegister) -> TokenResponse:
    """Crea organización, usuario y base de datos org de forma atómica.

    Orden:
    1. INSERT organizations → obtiene org_id
    2. Hash password e INSERT users
    3. create_org_database(org_id, business_type) — crea DB dedicada
    4. Retorna access_token + refresh_token

    Si el INSERT de users falla, se revierte la organización.
    """
    pool = await get_main_pool()

    async with pool.acquire() as conn:
        # 1. Crear organización
        org_row = await conn.fetchrow(
            """
            INSERT INTO organizations (name, sector, size, nit, city, plan_type, max_records)
            VALUES ($1, $2, $3, $4, $5, 'free', 10000)
            RETURNING id, name, sector, size, plan_type
            """,
            body.org_name,
            body.sector,
            body.size,
            body.nit,
            body.city,
        )
        if not org_row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo crear la organización.",
            )
        org_id: str = str(org_row["id"])

        # Verificar email único
        existing = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", body.email
        )
        if existing:
            # Revertir organización
            await conn.execute("DELETE FROM organizations WHERE id = $1", org_row["id"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo ya está registrado.",
            )

        # 2. Crear usuario
        try:
            user_row = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, full_name, org_id, role)
                VALUES ($1, $2, $3, $4, 'owner')
                RETURNING id, email, full_name, role, created_at
                """,
                body.email,
                hash_password(body.password),
                body.full_name,
                org_row["id"],
            )
        except Exception as exc:
            logger.error("Error creando usuario (org_id=%s): %s", org_id, exc)
            await conn.execute("DELETE FROM organizations WHERE id = $1", org_row["id"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo registrar el usuario.",
            )

    user_id: str = str(user_row["id"])

    # 3. Crear base de datos dedicada para la org.
    # Si falla, revertimos org+user para no dejar un usuario sin BD
    # (no podría usar la plataforma). El usuario puede reintentar el registro.
    # SIN hojas de plantilla por defecto. Antes se creaba el pack "servicios" para TODAS las organizaciones porque
    # `sector` (terciario, cuaternario, TIC, salud, educacion, comercio) nunca coincide con los packs de plantillas
    # (ferreteria, servicios, restaurante): cada dueno veia hojas vacias que no eran suyas y la carga podia
    # sumarles datos. Ahora la organizacion nace vacia: lo que suba define sus hojas (carga inteligente) y las
    # plantillas solo se crean si la persona elige un tipo de negocio (POST /api/v1/templates/initialize).
    try:
        await create_org_database(org_id, None)
    except Exception as exc:
        logger.error("Error creando DB de org (org_id=%s): %s", org_id, exc)
        # Revertir para no dejar un usuario huérfano sin BD operativa.
        try:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM users WHERE id = $1", user_row["id"])
                await conn.execute("DELETE FROM organizations WHERE id = $1", org_row["id"])
        except Exception as cleanup_exc:
            logger.error("Error en cleanup de registro fallido: %s", cleanup_exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "No se pudo crear la base de datos de tu organización. "
                "Por favor intenta registrarte de nuevo. Si el problema persiste, "
                "contacta al administrador."
            ),
        )

    # 4. Emitir tokens
    access_token = create_access_token(
        user_id=user_id,
        org_id=org_id,
        email=body.email,
        role="owner",
    )
    refresh_token = create_refresh_token(user_id=user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=3600,
    )


async def login_user(body: UserLogin) -> TokenResponse:
    """Autentica usuario con email/password y retorna tokens JWT."""
    pool = await get_main_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, email, password_hash, full_name, org_id, role
            FROM users
            WHERE email = $1
            """,
            body.email,
        )

    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas.",
        )

    user_id = str(row["id"])
    org_id = str(row["org_id"])

    # Actualizar last_login_at
    pool = await get_main_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_login_at = NOW() WHERE id = $1",
            row["id"],
        )

    access_token = create_access_token(
        user_id=user_id,
        org_id=org_id,
        email=row["email"],
        role=row["role"],
    )
    refresh_token = create_refresh_token(user_id=user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=3600,
    )


async def get_user_profile(user_id: str, org_id: str) -> UserProfileResponse:
    """Obtiene el perfil básico del usuario autenticado."""
    pool = await get_main_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, email, full_name, org_id, role, avatar_url, created_at
            FROM users
            WHERE id = $1 AND org_id = $2
            """,
            user_id,
            org_id,
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil no encontrado.",
        )

    return UserProfileResponse(
        user_id=str(row["id"]),
        org_id=str(row["org_id"]),
        email=row["email"],
        full_name=row["full_name"],
        role=row["role"],
        avatar_url=row["avatar_url"],
        created_at=row["created_at"],
    )


async def get_detailed_profile(user_id: str, org_id: str) -> ProfileResponse:
    """Obtiene el perfil detallado con preferencias y datos de la organización."""
    pool = await get_main_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                u.id, u.email, u.full_name, u.org_id, u.role,
                u.phone, u.avatar_url, u.preferences, u.last_login_at, u.created_at,
                o.name AS org_name, o.sector AS org_sector, o.plan_type AS org_plan
            FROM users u
            JOIN organizations o ON o.id = u.org_id
            WHERE u.id = $1 AND u.org_id = $2
            """,
            user_id,
            org_id,
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil no encontrado.",
        )

    return ProfileResponse(
        user_id=str(row["id"]),
        org_id=str(row["org_id"]),
        email=row["email"],
        full_name=row["full_name"],
        role=row["role"],
        phone=row["phone"],
        avatar_url=row["avatar_url"],
        preferences=row["preferences"] if isinstance(row["preferences"], dict) else {},
        org_name=row["org_name"],
        org_sector=row["org_sector"],
        org_plan=row["org_plan"] or "free",
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )


async def update_user_profile(
    user_id: str,
    org_id: str,
    body: ProfileUpdateRequest,
) -> UserProfileResponse:
    """Actualiza parcialmente el perfil. Solo los campos presentes se modifican.

    No permite cambiar email ni role.
    """
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Se debe enviar al menos un campo para actualizar.",
        )

    # Whitelist explícito para evitar SQL injection por nombre de columna
    ALLOWED_PROFILE_FIELDS = frozenset({"full_name", "phone", "avatar_url", "preferences"})
    for field in list(updates.keys()):
        if field not in ALLOWED_PROFILE_FIELDS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Campo no permitido.",
            )

    # Construir SET clause dinámicamente con parámetros posicionales
    set_clauses: list[str] = []
    values: list = []
    param_idx = 1

    for field, value in updates.items():
        set_clauses.append(f"{field} = ${param_idx}")
        values.append(value)
        param_idx += 1

    set_clauses.append(f"updated_at = NOW()")
    values.extend([user_id, org_id])

    pool = await get_main_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE users
            SET {', '.join(set_clauses)}
            WHERE id = ${param_idx} AND org_id = ${param_idx + 1}
            RETURNING id, email, full_name, org_id, role, avatar_url, created_at
            """,
            *values,
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil no encontrado.",
        )

    return UserProfileResponse(
        user_id=str(row["id"]),
        org_id=str(row["org_id"]),
        email=row["email"],
        full_name=row["full_name"],
        role=row["role"],
        avatar_url=row["avatar_url"],
        created_at=row["created_at"],
    )
