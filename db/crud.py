"""
CRUD — operaciones de base de datos para Project y GeneratedFile
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from db.models import Project, GeneratedFile


# ── Project CRUD ──────────────────────────────────────────────────────────────

def create_project(db: Session, name: str, tramo: str = "", dm_ini: str = "",
                   dm_fin: str = "", ingeniero: str = "",
                   project_data: dict | None = None) -> Project:
    """Crear un nuevo proyecto."""
    p = Project(
        name=name,
        tramo=tramo,
        dm_ini=dm_ini,
        dm_fin=dm_fin,
        ingeniero=ingeniero,
    )
    p.set_data(project_data or {})
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def get_project(db: Session, project_id: int) -> Optional[Project]:
    """Obtener proyecto por ID."""
    return db.query(Project).filter(Project.id == project_id).first()


def list_projects(db: Session, status: str = "activo",
                  limit: int = 100, offset: int = 0) -> list[Project]:
    """Listar proyectos por estado (activo / archivado)."""
    q = db.query(Project)
    if status != "todos":
        q = q.filter(Project.status == status)
    return (q.order_by(Project.updated_at.desc())
              .limit(limit)
              .offset(offset)
              .all())


def update_project(db: Session, project_id: int, **kwargs) -> Optional[Project]:
    """Actualizar campos de un proyecto (name, tramo, dm_ini, dm_fin, ingeniero, status)."""
    p = get_project(db, project_id)
    if not p:
        return None
    allowed = {"name", "tramo", "dm_ini", "dm_fin", "ingeniero", "status"}
    for key, val in kwargs.items():
        if key in allowed:
            setattr(p, key, val)
    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(p)
    return p


def save_project_data(db: Session, project_id: int,
                      project_data: dict) -> Optional[Project]:
    """Persistir el JSON de cálculo de un proyecto."""
    p = get_project(db, project_id)
    if not p:
        return None
    p.set_data(project_data)
    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(p)
    return p


def archive_project(db: Session, project_id: int) -> Optional[Project]:
    """Archivar un proyecto (soft delete)."""
    return update_project(db, project_id, status="archivado")


def restore_project(db: Session, project_id: int) -> Optional[Project]:
    """Restaurar un proyecto archivado."""
    return update_project(db, project_id, status="activo")


def delete_project(db: Session, project_id: int) -> bool:
    """Eliminar proyecto definitivamente (hard delete)."""
    p = get_project(db, project_id)
    if not p:
        return False
    db.delete(p)
    db.commit()
    return True


def count_projects(db: Session, status: str = "activo") -> int:
    q = db.query(Project)
    if status != "todos":
        q = q.filter(Project.status == status)
    return q.count()


# ── GeneratedFile CRUD ────────────────────────────────────────────────────────

def create_generated_file(db: Session, project_id: int, file_type: str,
                          file_name: str, storage_key: str,
                          storage_url: str = "", file_size_kb: float = 0.0) -> GeneratedFile:
    """Registrar un archivo generado."""
    gf = GeneratedFile(
        project_id=project_id,
        file_type=file_type,
        file_name=file_name,
        storage_key=storage_key,
        storage_url=storage_url,
        file_size_kb=file_size_kb,
    )
    db.add(gf)
    db.commit()
    db.refresh(gf)
    return gf


def list_files_for_project(db: Session, project_id: int,
                            file_type: str | None = None) -> list[GeneratedFile]:
    """Listar archivos de un proyecto, opcionalmente filtrado por tipo."""
    q = (db.query(GeneratedFile)
           .filter(GeneratedFile.project_id == project_id)
           .order_by(GeneratedFile.created_at.desc()))
    if file_type:
        q = q.filter(GeneratedFile.file_type == file_type)
    return q.all()


def list_all_files(db: Session, limit: int = 200) -> list[GeneratedFile]:
    """Listar todos los archivos generados (para vista de administración)."""
    return (db.query(GeneratedFile)
              .order_by(GeneratedFile.created_at.desc())
              .limit(limit)
              .all())


def delete_generated_file(db: Session, file_id: int) -> Optional[GeneratedFile]:
    """Eliminar registro de archivo (no elimina del storage)."""
    gf = db.query(GeneratedFile).filter(GeneratedFile.id == file_id).first()
    if not gf:
        return None
    db.delete(gf)
    db.commit()
    return gf


def get_generated_file(db: Session, file_id: int) -> Optional[GeneratedFile]:
    return db.query(GeneratedFile).filter(GeneratedFile.id == file_id).first()
