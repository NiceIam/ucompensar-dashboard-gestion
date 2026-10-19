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
    # Tope de espera del chat (segundos). Es el presupuesto TOTAL de un mensaje: todas las llamadas a Gemini
    # y las herramientas del bucle. Al excederlo el usuario recibe el fallback "timeout".
    GEMINI_TIMEOUT_SECONDS: float = 25.0
    # Tokens de salida por llamada del chat. OJO: en los modelos con razonamiento ("thinking") ese razonamiento
    # se descuenta de este mismo tope; si se agota, Gemini corta con MAX_TOKENS sin texto util (fallback
    # "truncated") y aun asi cobra todo lo generado. Es un tope, no un gasto: se cobra lo que se genera. 2048
    # es el valor con el que el chat funcionaba antes de este cambio; con razonamiento largo, subirlo.
    GEMINI_CHAT_MAX_OUTPUT_TOKENS: int = 2048
    # Nivel de razonamiento del chat (ThinkingConfig.thinking_level: minimal | low | medium | high).
    # Vacio = no se envia y el modelo usa su default. No se activa por defecto: no esta verificado con una
    # llamada real que el modelo configurado lo acepte (un valor no soportado haria fallar cada mensaje).
    GEMINI_THINKING_LEVEL: str = ""
    # Carga inteligente (agente de esquema): UNA llamada a Gemini por hoja AMBIGUA (las claras no llaman). Tope
    # de espera por llamada, tope de tokens de salida (incluye el razonamiento), nivel de razonamiento ("low"
    # esta probado con el modelo configurado; vacio = default del modelo) y topes de gasto: llamadas por
    # peticion y por organizacion por hora (en memoria de cada instancia: es un freno, no un contador exacto).
    # INTAKE_AI_ENABLED=False deja solo el resultado determinista.
    INTAKE_AI_ENABLED: bool = True
    INTAKE_AI_TIMEOUT_SECONDS: float = 20.0
    INTAKE_AI_MAX_OUTPUT_TOKENS: int = 1200
    INTAKE_THINKING_LEVEL: str = "low"
    INTAKE_AI_MAX_CALLS_PER_REQUEST: int = 8
    INTAKE_AI_MAX_CALLS_PER_ORG_HOUR: int = 40
    # Function calling del chat: una ronda = el modelo pide herramientas y el servidor las ejecuta. Tras la
    # ultima ronda el modelo debe responder con texto, asi que un mensaje hace como maximo rondas + 1 llamadas.
    CHAT_MAX_TOOL_ROUNDS: int = 4
    # Cotas de lo que una herramienta le devuelve al modelo (cada caracter vuelve a costar en la ronda siguiente).
    CHAT_TOOL_MAX_ROWS: int = 50
    CHAT_TOOL_MAX_CHARS: int = 3000
    # Presupuesto ACUMULADO de caracteres de resultados de herramientas por mensaje (todas las rondas). Al
    # agotarse, las siguientes consultas devuelven un error corto y el modelo responde con lo que ya tiene.
    CHAT_TOOL_MAX_TOTAL_CHARS: int = 6000
    # Columnas con estadisticas por llamada a describe_table (las primeras del catalogo). Cada columna cuesta
    # leer y contar toda la tabla: con 40 columnas x 50k filas se rozaba el statement_timeout de 8 s.
    CHAT_DESCRIBE_MAX_COLUMNS: int = 12
    # Mensajes al chat permitidos por usuario (formato slowapi). Cada mensaje consume la API key compartida de Gemini.
    CHAT_RATE_LIMIT: str = "20/minute"
    # Topes COMPARTIDOS entre instancias (se cuentan en Postgres sobre chat_messages, role='user').
    # El de la organizacion por dia es el que protege el costo de la API key compartida de Gemini.
    # Un valor <= 0 desactiva ese tope.
    CHAT_USER_MAX_MESSAGES: int = 20
    CHAT_USER_WINDOW_SECONDS: int = 60
    CHAT_ORG_DAILY_MESSAGES: int = 300

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
