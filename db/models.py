"""
Modelos ORM — Cuadros de Carga Platform
  Project      — proyecto con metadatos y datos de cálculo (JSON)
  GeneratedFile — archivos PDF/Excel generados y almacenados
"""
import json
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Text, Float,
    DateTime, ForeignKey, Boolean, func,
)
from sqlalchemy.orm import relationship

from db.database import Base


def _now():
    return datetime.now(timezone.utc)


class Project(Base):
    """Proyecto de Cuadro de Cargas.

    project_data contiene el estado completo de la aplicación en JSON:
    {
      "metadata": {nombre, tramo, dm_ini, dm_fin, ingeniero},
      "n_empalmes": int,
      "empalmes": [
        {
          "emp_id": "E-01", "tipo": "3F",
          "i_cc": 1500.0, "t_prot": 0.4, "aislamiento": "XLPE",
          "n_ctos": 3,
          "circuitos": [
            {
              "cto_num": 1, "material": "AL", "fp": 0.95,
              "postes": [{"interdistancia_m": 35.0, "pot_w": 133.0, "fase": "R"}, ...]
            }
          ]
        }
      ]
    }
    """
    __tablename__ = "projects"

    id          = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name        = Column(String(200), nullable=False, index=True)
    tramo       = Column(String(200), default="")
    dm_ini      = Column(String(50),  default="")
    dm_fin      = Column(String(50),  default="")
    ingeniero   = Column(String(200), default="")
    project_data = Column(Text, default="{}")   # JSON serializado
    status      = Column(String(20),  default="activo")   # activo | archivado
    created_at  = Column(DateTime(timezone=True), default=_now, server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    # Relación 1:N con archivos generados
    files = relationship(
        "GeneratedFile",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="GeneratedFile.created_at.desc()",
    )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        """Deserializar project_data a dict."""
        try:
            return json.loads(self.project_data or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_data(self, data: dict):
        """Serializar dict a JSON y guardar en project_data."""
        self.project_data = json.dumps(data, ensure_ascii=False)

    def summary(self) -> dict:
        """Resumen ligero para listados."""
        data = self.get_data()
        empalmes = data.get("empalmes", [])
        return {
            "id":         self.id,
            "name":       self.name,
            "tramo":      self.tramo,
            "dm_ini":     self.dm_ini,
            "dm_fin":     self.dm_fin,
            "ingeniero":  self.ingeniero,
            "status":     self.status,
            "n_empalmes": len(empalmes),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __repr__(self):
        return f"<Project id={self.id} name={self.name!r} status={self.status}>"


class GeneratedFile(Base):
    """Archivo PDF o Excel generado y almacenado."""
    __tablename__ = "generated_files"

    id           = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id   = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    file_type    = Column(String(10), nullable=False)   # pdf | xlsx
    file_name    = Column(String(255), nullable=False)
    storage_key  = Column(String(500), nullable=False)  # path local o key S3
    storage_url  = Column(String(1000), default="")     # URL pública / presigned
    file_size_kb = Column(Float, default=0.0)
    created_at   = Column(DateTime(timezone=True), default=_now, server_default=func.now())

    project = relationship("Project", back_populates="files")

    def __repr__(self):
        return (f"<GeneratedFile id={self.id} project_id={self.project_id} "
                f"type={self.file_type} name={self.file_name!r}>")
