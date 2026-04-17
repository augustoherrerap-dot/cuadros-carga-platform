"""
Configuración central de la aplicación — Pydantic Settings
Soporta SQLite (desarrollo) y PostgreSQL (producción)
Soporta almacenamiento local, S3, MinIO y Cloudflare R2
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "Cuadros de Carga — Alumbrado Público"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = Field(default=False)

    # ── Base de datos ─────────────────────────────────────────────────────────
    # SQLite (desarrollo): "sqlite:///./cuadros_carga.db"
    # PostgreSQL (producción): "postgresql+psycopg2://user:pass@host:5432/dbname"
    DATABASE_URL: str = Field(
        default=f"sqlite:///{BASE_DIR}/cuadros_carga.db",
        description="URL de conexión a la base de datos",
    )

    # ── Almacenamiento ────────────────────────────────────────────────────────
    # local | s3 | minio | r2
    STORAGE_TYPE: str = Field(default="local", description="local | s3 | minio | r2")
    STORAGE_LOCAL_PATH: str = Field(
        default=str(BASE_DIR / "uploads"),
        description="Ruta local para archivos generados (solo STORAGE_TYPE=local)",
    )

    # AWS S3 / MinIO / Cloudflare R2
    AWS_ACCESS_KEY_ID: str = Field(default="")
    AWS_SECRET_ACCESS_KEY: str = Field(default="")
    AWS_REGION: str = Field(default="us-east-1")
    S3_BUCKET_NAME: str = Field(default="cuadros-carga")
    S3_ENDPOINT_URL: str = Field(
        default="",
        description="URL endpoint para MinIO o R2 (vacío para AWS S3 nativo)",
    )
    S3_PUBLIC_URL_BASE: str = Field(
        default="",
        description="URL base pública del bucket (opcional, para URLs directas)",
    )
    PRESIGNED_URL_EXPIRES: int = Field(default=3600, description="Tiempo validez URL firmada [s]")

    # ── Seguridad ─────────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(
        default="cambia-esta-clave-en-produccion-32chars-min",
        description="Clave secreta para tokens y sesiones",
    )

    # ── Streamlit (opcionales, para docker/render) ────────────────────────────
    STREAMLIT_SERVER_PORT: int = Field(default=8501)
    STREAMLIT_SERVER_ADDRESS: str = Field(default="0.0.0.0")


# Singleton global
settings = Settings()

# Crear carpeta local de uploads si corresponde
if settings.STORAGE_TYPE == "local":
    Path(settings.STORAGE_LOCAL_PATH).mkdir(parents=True, exist_ok=True)
