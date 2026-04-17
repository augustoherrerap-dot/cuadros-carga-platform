"""
Página de Archivos Generados — listado, descarga y eliminación
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from datetime import datetime

from db.database import init_db, SessionLocal
from db.crud import (
    list_files_for_project, list_all_files,
    list_projects, get_generated_file, delete_generated_file,
    get_project,
)
from storage.client import get_storage

init_db()

st.set_page_config(
    page_title="Archivos — Cuadros de Carga",
    page_icon="📁",
    layout="wide",
)

st.markdown("""
<style>
  .block-container{padding-top:1rem;}
  .sec-hdr{background:#1F3864;color:white;border-radius:6px;
    padding:5px 12px;margin:10px 0 4px 0;font-weight:700;font-size:.88rem;}
  .badge-pdf{background:#FFE0E0;color:#9C0006;border-radius:4px;
    padding:2px 7px;font-size:.74rem;font-weight:700;}
  .badge-xlsx{background:#E0FFE0;color:#375623;border-radius:4px;
    padding:2px 7px;font-size:.74rem;font-weight:700;}
  h1{color:#1F3864;}
</style>
""", unsafe_allow_html=True)

st.title("📁 Archivos Generados")
st.caption("Historial de PDFs y Excels generados por proyecto")

# ── Filtros ───────────────────────────────────────────────────────────────────
db = SessionLocal()
try:
    proyectos = list_projects(db, status="todos", limit=200)
    all_files = list_all_files(db, limit=500)
finally:
    db.close()

f1, f2, f3 = st.columns([3, 2, 1])
with f1:
    proj_map = {"Todos los proyectos": None}
    for p in proyectos:
        proj_map[f"#{p.id} — {p.name}"] = p.id
    filtro_proj = f1.selectbox("Proyecto", list(proj_map.keys()))

with f2:
    filtro_tipo = f2.selectbox("Tipo", ["Todos", "pdf", "xlsx"])

with f3:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Actualizar", use_container_width=True):
        st.rerun()

# Aplicar filtros
pid_filtro  = proj_map[filtro_proj]
tipo_filtro = None if filtro_tipo == "Todos" else filtro_tipo

db = SessionLocal()
try:
    if pid_filtro is not None:
        files = list_files_for_project(db, pid_filtro, file_type=tipo_filtro)
    else:
        files = list_all_files(db, limit=500)
        if tipo_filtro:
            files = [f for f in files if f.file_type == tipo_filtro]
finally:
    db.close()

# ── Estadísticas ──────────────────────────────────────────────────────────────
n_pdf  = sum(1 for f in files if f.file_type == "pdf")
n_xlsx = sum(1 for f in files if f.file_type == "xlsx")
size_t = sum(f.file_size_kb for f in files)

m1, m2, m3 = st.columns(3)
m1.metric("PDFs", n_pdf)
m2.metric("Excels", n_xlsx)
m3.metric("Tamaño total", f"{size_t/1024:.1f} MB" if size_t > 1024 else f"{size_t:.0f} KB")

st.markdown("---")

# ── Lista de archivos ─────────────────────────────────────────────────────────
if not files:
    st.info("No hay archivos generados con los filtros seleccionados.")
    st.stop()

st.markdown(f"**{len(files)} archivo(s) encontrado(s)**")
st.markdown('<div class="sec-hdr">Archivos Generados</div>', unsafe_allow_html=True)

storage = get_storage()

for f in files:
    tipo_badge = (
        '<span class="badge-pdf">PDF</span>' if f.file_type == "pdf"
        else '<span class="badge-xlsx">XLSX</span>'
    )
    created_str = (f.created_at.strftime("%d/%m/%Y %H:%M")
                   if f.created_at else "—")
    size_str = f"{f.file_size_kb:.1f} KB" if f.file_size_kb else "—"

    # Obtener nombre del proyecto
    db = SessionLocal()
    try:
        proj = get_project(db, f.project_id)
        proj_name = proj.name if proj else f"#{f.project_id}"
    finally:
        db.close()

    col1, col2, col3, col4, col5 = st.columns([3, 2, 1.5, 1.5, 1.5])
    with col1:
        st.markdown(
            f"{tipo_badge} &nbsp; **{f.file_name}**",
            unsafe_allow_html=True,
        )
        st.caption(f"Proyecto: {proj_name}  |  ID archivo: #{f.id}")
    with col2:
        st.caption(f"🕐 {created_str}")
    with col3:
        st.caption(f"📦 {size_str}")
    with col4:
        # Botón de descarga
        try:
            if storage.exists(f.storage_key):
                file_bytes = storage.download(f.storage_key)
                mime = ("application/pdf" if f.file_type == "pdf"
                        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                st.download_button(
                    "⬇️ Descargar",
                    data=file_bytes,
                    file_name=f.file_name,
                    mime=mime,
                    key=f"dl_{f.id}",
                    use_container_width=True,
                )
            else:
                st.caption("⚠️ Archivo no disponible en storage")
        except Exception as ex:
            st.caption(f"⚠️ Error: {ex}")
    with col5:
        key_confirm = f"confirm_del_file_{f.id}"
        if st.button("🗑️", key=f"del_file_{f.id}", use_container_width=True,
                     help="Eliminar registro y archivo"):
            st.session_state[key_confirm] = True

        if st.session_state.get(key_confirm, False):
            st.warning("¿Eliminar?")
            c1, c2 = st.columns(2)
            if c1.button("Sí", key=f"del_ok_f_{f.id}"):
                # Eliminar del storage
                storage.delete(f.storage_key)
                # Eliminar de BD
                db2 = SessionLocal()
                try:
                    delete_generated_file(db2, f.id)
                finally:
                    db2.close()
                st.session_state.pop(key_confirm, None)
                st.rerun()
            if c2.button("No", key=f"del_no_f_{f.id}"):
                st.session_state.pop(key_confirm, None)
                st.rerun()

    st.divider()
