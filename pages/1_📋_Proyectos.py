"""
Página de gestión de proyectos — CRUD completo
Crear, editar, archivar, restaurar y eliminar proyectos
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from datetime import date

from db.database import init_db, SessionLocal
from db.crud import (
    create_project, get_project, list_projects,
    update_project, save_project_data,
    archive_project, restore_project, delete_project,
    count_projects,
)

init_db()

st.set_page_config(
    page_title="Proyectos — Cuadros de Carga",
    page_icon="📋",
    layout="wide",
)

st.markdown("""
<style>
  .block-container{padding-top:1rem;}
  .sec-hdr{background:#1F3864;color:white;border-radius:6px;
    padding:5px 12px;margin:10px 0 4px 0;font-weight:700;font-size:.88rem;}
  .badge-active{background:#C6EFCE;color:#375623;border-radius:4px;
    padding:2px 7px;font-size:.74rem;font-weight:700;}
  .badge-archived{background:#F2F2F2;color:#666;border-radius:4px;
    padding:2px 7px;font-size:.74rem;font-weight:700;}
  h1{color:#1F3864;}
</style>
""", unsafe_allow_html=True)

st.title("📋 Gestión de Proyectos")
st.caption("Crear, editar, archivar y eliminar proyectos de Cuadros de Carga")


# ── Filtro de estado ──────────────────────────────────────────────────────────
filtro_col, _, nuevo_col = st.columns([2, 4, 2])
with filtro_col:
    filtro = st.selectbox("Mostrar", ["Activos", "Archivados", "Todos"],
                          label_visibility="collapsed")

estado_map = {"Activos": "activo", "Archivados": "archivado", "Todos": "todos"}
estado_filtro = estado_map[filtro]

with nuevo_col:
    if st.button("➕ Nuevo Proyecto", type="primary", use_container_width=True):
        st.session_state["show_create_form"] = True


# ── Formulario de creación ────────────────────────────────────────────────────
if st.session_state.get("show_create_form", False):
    st.markdown('<div class="sec-hdr">➕ Nuevo Proyecto</div>', unsafe_allow_html=True)
    with st.form("form_create_project"):
        f1, f2 = st.columns(2)
        nombre    = f1.text_input("Nombre del proyecto *", placeholder="Ampliación Ruta 5 Norte")
        tramo     = f2.text_input("Tramo / Ruta", placeholder="V-A Ruta 5")
        f3, f4    = st.columns(2)
        dm_ini    = f3.text_input("DM Inicial", placeholder="94.457")
        dm_fin    = f4.text_input("DM Final",   placeholder="128.360")
        f5, f6    = st.columns(2)
        ingeniero = f5.text_input("Ingeniero responsable")
        _fecha    = f6.date_input("Fecha", value=date.today())

        c_ok, c_cancel = st.columns(2)
        submitted = c_ok.form_submit_button("✅ Crear Proyecto", type="primary",
                                             use_container_width=True)
        cancel    = c_cancel.form_submit_button("❌ Cancelar", use_container_width=True)

    if cancel:
        st.session_state["show_create_form"] = False
        st.rerun()

    if submitted:
        if not nombre.strip():
            st.error("El nombre del proyecto es obligatorio.")
        else:
            db = SessionLocal()
            try:
                p = create_project(
                    db,
                    name=nombre.strip(),
                    tramo=tramo.strip(),
                    dm_ini=dm_ini.strip(),
                    dm_fin=dm_fin.strip(),
                    ingeniero=ingeniero.strip(),
                    project_data={
                        "metadata": {
                            "nombre": nombre.strip(),
                            "tramo": tramo.strip(),
                            "dm_ini": dm_ini.strip(),
                            "dm_fin": dm_fin.strip(),
                            "ingeniero": ingeniero.strip(),
                            "fecha": str(_fecha),
                        },
                        "n_empalmes": 1,
                        "empalmes": [],
                    },
                )
                st.session_state["show_create_form"] = False
                st.session_state["active_project_id"]   = p.id
                st.session_state["active_project_name"] = p.name
                st.success(f"✅ Proyecto **{p.name}** creado con ID #{p.id}")
                st.info("Ahora puedes ir a ⚡ Cálculo para ingresar los datos eléctricos.")
            except Exception as e:
                st.error(f"Error al crear proyecto: {e}")
            finally:
                db.close()
            st.rerun()

st.markdown("---")


# ── Lista de proyectos ────────────────────────────────────────────────────────
db = SessionLocal()
try:
    proyectos = list_projects(db, status=estado_filtro, limit=100)
finally:
    db.close()

if not proyectos:
    st.info(f"No hay proyectos {'activos' if estado_filtro == 'activo' else 'en este estado'}.")
    st.stop()

st.markdown(f"**{len(proyectos)} proyecto(s) encontrado(s)**")

for p in proyectos:
    data  = p.get_data()
    n_emp = len(data.get("empalmes", []))
    upd   = p.updated_at
    upd_str = upd.strftime("%d/%m/%Y %H:%M") if upd else "—"

    is_active = p.status == "activo"

    with st.expander(
        f"{'🟢' if is_active else '⚪'} #{p.id} — {p.name}  |  "
        f"Tramo: {p.tramo or '—'}  |  "
        f"DM {p.dm_ini or '—'} – {p.dm_fin or '—'}  |  "
        f"{'activo' if is_active else 'archivado'}  |  "
        f"Últ. modif.: {upd_str}",
        expanded=False,
    ):
        # Vista del proyecto
        col_info, col_actions = st.columns([3, 1])
        with col_info:
            st.markdown(f"**Proyecto:** {p.name}")
            st.markdown(f"**Tramo:** {p.tramo or '—'}  |  **DM:** {p.dm_ini or '—'} – {p.dm_fin or '—'}")
            st.markdown(f"**Ingeniero:** {p.ingeniero or '—'}")
            st.markdown(f"**Empalmes guardados:** {n_emp}")
            st.markdown(f"**Creado:** {p.created_at.strftime('%d/%m/%Y %H:%M') if p.created_at else '—'}")
            st.markdown(f"**Modificado:** {upd_str}")

        with col_actions:
            st.markdown("**Acciones:**")

            if is_active:
                if st.button("⚡ Abrir en Cálculo", key=f"calc_{p.id}",
                             type="primary", use_container_width=True):
                    st.session_state["active_project_id"]   = p.id
                    st.session_state["active_project_name"] = p.name
                    st.switch_page("pages/2_⚡_Cálculo.py")

            # Formulario de edición
            if st.button("✏️ Editar Metadatos", key=f"edit_{p.id}",
                         use_container_width=True):
                st.session_state[f"edit_mode_{p.id}"] = True

            if is_active:
                if st.button("🗄️ Archivar", key=f"arch_{p.id}",
                             use_container_width=True):
                    db = SessionLocal()
                    try:
                        archive_project(db, p.id)
                    finally:
                        db.close()
                    st.rerun()
            else:
                if st.button("♻️ Restaurar", key=f"rest_{p.id}",
                             use_container_width=True):
                    db = SessionLocal()
                    try:
                        restore_project(db, p.id)
                    finally:
                        db.close()
                    st.rerun()

            # Eliminar (con confirmación)
            key_confirm = f"confirm_del_{p.id}"
            if st.button("🗑️ Eliminar", key=f"del_{p.id}",
                         use_container_width=True):
                st.session_state[key_confirm] = True

            if st.session_state.get(key_confirm, False):
                st.warning("⚠️ ¿Eliminar definitivamente? Esta acción no se puede deshacer.")
                c1, c2 = st.columns(2)
                if c1.button("Sí, eliminar", key=f"del_ok_{p.id}", type="primary"):
                    db = SessionLocal()
                    try:
                        delete_project(db, p.id)
                    finally:
                        db.close()
                    st.session_state.pop(key_confirm, None)
                    st.rerun()
                if c2.button("Cancelar", key=f"del_no_{p.id}"):
                    st.session_state.pop(key_confirm, None)
                    st.rerun()

        # ── Formulario de edición de metadatos ────────────────────────────────
        if st.session_state.get(f"edit_mode_{p.id}", False):
            st.markdown("---")
            st.markdown("**✏️ Editar metadatos del proyecto:**")
            with st.form(f"form_edit_{p.id}"):
                e1, e2 = st.columns(2)
                new_name  = e1.text_input("Nombre", value=p.name)
                new_tramo = e2.text_input("Tramo",  value=p.tramo or "")
                e3, e4    = st.columns(2)
                new_dmi   = e3.text_input("DM Inicial", value=p.dm_ini or "")
                new_dmf   = e4.text_input("DM Final",   value=p.dm_fin or "")
                new_ing   = st.text_input("Ingeniero",  value=p.ingeniero or "")
                s1, s2    = st.columns(2)
                save_b  = s1.form_submit_button("💾 Guardar", type="primary", use_container_width=True)
                canc_b  = s2.form_submit_button("Cancelar", use_container_width=True)

            if save_b:
                db = SessionLocal()
                try:
                    update_project(db, p.id,
                        name=new_name.strip(), tramo=new_tramo.strip(),
                        dm_ini=new_dmi.strip(), dm_fin=new_dmf.strip(),
                        ingeniero=new_ing.strip())
                    # Actualizar también metadata dentro del JSON
                    proj_ref = get_project(db, p.id)
                    if proj_ref:
                        pdata = proj_ref.get_data()
                        pdata.setdefault("metadata", {})
                        pdata["metadata"].update({
                            "nombre": new_name.strip(), "tramo": new_tramo.strip(),
                            "dm_ini": new_dmi.strip(), "dm_fin": new_dmf.strip(),
                            "ingeniero": new_ing.strip(),
                        })
                        save_project_data(db, p.id, pdata)
                finally:
                    db.close()
                st.session_state.pop(f"edit_mode_{p.id}", None)
                st.rerun()

            if canc_b:
                st.session_state.pop(f"edit_mode_{p.id}", None)
                st.rerun()
