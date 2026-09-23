from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_INSECURE_SECRETS = {
    "",
    "dev-secret-key-change-in-production",
    "change-me",
    "secret",
    "changeme",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # PostgreSQL local
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "postgres"
    DATABASE_NAME: str = "pi_main"
    # False para Postgres local (Docker). True para proveedores hosted que
    # exigen SSL (ej. Neon) -- sin esto, asyncpg no negocia SSL y la
    # conexion falla contra ese tipo de proveedores.
    DATABASE_SSL: bool = False

    # Google AI
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GEMINI_MAX_TOKENS: int = 8192
    GEMINI_TEMPERATURE: float = 0.1

    # App
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = ""
    CORS_ORIGINS: str = "http://localhost:3000"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # Cookies
    # Secure flag: si None, se deriva de is_production (default seguro).
    # Override explicito a False solo en deploys HTTP-only sin TLS (ej. VPS sin certificado).
    COOKIES_SECURE: bool | None = None
    # "strict"/"lax" cuando frontend y backend comparten dominio (VPS con proxy).
    # "none" cuando viven en dominios/sitios distintos (ej. dos proyectos de
    # Vercel: *.vercel.app esta en la Public Suffix List, asi que cada
    # subdominio es un "site" distinto para el navegador -- con strict/lax
    # la cookie nunca se envia en las llamadas fetch() del frontend al backend.
    COOKIES_SAMESITE: str = "strict"

    @field_validator("COOKIES_SAMESITE", mode="after")
    @classmethod
    def _validate_samesite(cls, v: str) -> str:
        v = v.lower()
        if v not in ("strict", "lax", "none"):
            raise ValueError("COOKIES_SAMESITE debe ser 'strict', 'lax' o 'none'.")
        return v

    @field_validator("APP_SECRET_KEY", mode="after")
    @classmethod
    def _validate_secret(cls, v: str) -> str:
        if v in _INSECURE_SECRETS or len(v) < 32:
            raise ValueError(
                "APP_SECRET_KEY debe estar definida en el entorno y tener al menos 32 "
                "caracteres. Genera una con `python -c \"import secrets; "
                "print(secrets.token_urlsafe(48))\"` y colócala en backend/.env."
            )
        return v

    # bcrypt
    BCRYPT_ROUNDS: int = 12

    @field_validator("BCRYPT_ROUNDS", mode="after")
    @classmethod
    def _validate_bcrypt_rounds(cls, v: int) -> int:
        if v < 10 or v > 15:
            raise ValueError("BCRYPT_ROUNDS debe estar entre 10 y 15.")
        return v

    # Rate limiting
    MAX_REQUESTS_PER_MINUTE: int = 60

    # Retry configuration
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_BASE_DELAY: float = 1.0
    RETRY_MAX_DELAY: float = 30.0

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        return v

    def get_cors_origins_list(self) -> List[str]:
        return [
            origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cookies_secure_effective(self) -> bool:
        """Secure flag efectivo para set_cookie. None = derivar de is_production.

        SameSite=None exige Secure=True por especificacion -- los navegadores
        descartan la cookie si no, asi que se fuerza sin importar COOKIES_SECURE.
        """
        if self.COOKIES_SAMESITE == "none":
            return True
        if self.COOKIES_SECURE is None:
            return self.is_production
        return self.COOKIES_SECURE


@lru_cache
def get_settings() -> Settings:
    return Settings()
