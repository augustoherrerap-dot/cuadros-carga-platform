"""
Cliente de almacenamiento unificado
Backends soportados: local | s3 | minio | r2 (via boto3)
"""
from __future__ import annotations

import io
import os
import shutil
from pathlib import Path
from datetime import datetime, timezone


class StorageClient:
    """
    Interfaz única para operaciones de archivo:
      upload(key, data_bytes, content_type) → storage_url
      download(key) → bytes
      delete(key) → bool
      presigned_url(key, expires_in) → str
      exists(key) → bool
    """

    def __init__(self, settings=None):
        if settings is None:
            from config.settings import settings as _s
            settings = _s

        self.storage_type  = settings.STORAGE_TYPE.lower()
        self.local_path    = Path(settings.STORAGE_LOCAL_PATH)
        self.bucket        = settings.S3_BUCKET_NAME
        self.endpoint_url  = settings.S3_ENDPOINT_URL or None
        self.public_base   = settings.S3_PUBLIC_URL_BASE.rstrip("/")
        self.expires       = settings.PRESIGNED_URL_EXPIRES
        self._s3_client    = None

        if self.storage_type == "local":
            self.local_path.mkdir(parents=True, exist_ok=True)
        else:
            self._s3_client = self._build_s3(settings)

    # ── S3 client factory ─────────────────────────────────────────────────────

    def _build_s3(self, settings):
        try:
            import boto3
            kwargs = dict(
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            return boto3.client("s3", **kwargs)
        except ImportError as e:
            raise RuntimeError(
                "boto3 no está instalado. Ejecute: pip install boto3"
            ) from e

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload(self, key: str, data: bytes,
               content_type: str = "application/octet-stream") -> str:
        """
        Subir archivo.
        Returns: URL de acceso (path local o URL S3/presigned).
        """
        if self.storage_type == "local":
            dest = self.local_path / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return str(dest)
        else:
            self._s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            if self.public_base:
                return f"{self.public_base}/{key}"
            return self.presigned_url(key)

    # ── Download ──────────────────────────────────────────────────────────────

    def download(self, key: str) -> bytes:
        """Descargar archivo. Lanza FileNotFoundError si no existe."""
        if self.storage_type == "local":
            dest = self.local_path / key
            if not dest.exists():
                raise FileNotFoundError(f"Archivo no encontrado: {key}")
            return dest.read_bytes()
        else:
            buf = io.BytesIO()
            self._s3_client.download_fileobj(self.bucket, key, buf)
            buf.seek(0)
            return buf.read()

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete(self, key: str) -> bool:
        """Eliminar archivo del storage. Returns True si OK."""
        try:
            if self.storage_type == "local":
                dest = self.local_path / key
                if dest.exists():
                    dest.unlink()
            else:
                self._s3_client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    # ── Presigned URL ─────────────────────────────────────────────────────────

    def presigned_url(self, key: str, expires_in: int | None = None) -> str:
        """Generar URL firmada temporal (solo S3/MinIO/R2)."""
        if self.storage_type == "local":
            return str(self.local_path / key)
        exp = expires_in or self.expires
        return self._s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=exp,
        )

    # ── Exists ────────────────────────────────────────────────────────────────

    def exists(self, key: str) -> bool:
        """Verificar si el archivo existe."""
        if self.storage_type == "local":
            return (self.local_path / key).exists()
        try:
            self._s3_client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    # ── Key factory ──────────────────────────────────────────────────────────

    @staticmethod
    def build_key(project_id: int, file_type: str, file_name: str) -> str:
        """
        Construir storage key: proyectos/{id}/{year}/{file_name}
        Garantiza unicidad temporal para el mismo proyecto.
        """
        year = datetime.now(timezone.utc).strftime("%Y%m")
        safe_name = file_name.replace(" ", "_")
        return f"proyectos/{project_id}/{year}/{safe_name}"


# Singleton global
_storage_client: StorageClient | None = None


def get_storage() -> StorageClient:
    """Retorna (o crea) el cliente de storage singleton."""
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageClient()
    return _storage_client
