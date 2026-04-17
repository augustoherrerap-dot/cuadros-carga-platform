"""
Motor de base de datos — SQLAlchemy 2.0
Soporta SQLite (desarrollo) y PostgreSQL (producción)
"""
import sys
from pathlib import Path

# Resolver imports relativos desde cualquier contexto de ejecución
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config.settings import settings


# ── Engine ────────────────────────────────────────────────────────────────────

def _build_engine():
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=settings.DEBUG,
        )
        # Habilitar foreign keys en SQLite
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    else:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=settings.DEBUG,
        )
    return engine


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ── Base declarativa ──────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_db():
    """Dependency generator para obtener sesión de BD (compatible con FastAPI / uso directo)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Crear todas las tablas si no existen. Llamar una vez al iniciar la app."""
    from db import models  # noqa: F401 — importar para que SQLAlchemy los registre
    Base.metadata.create_all(bind=engine)
