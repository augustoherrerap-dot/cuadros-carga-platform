"""
Cuadros de Carga Platform — Dashboard principal
Aplicación web persistente con gestión de proyectos, PDF/Excel y almacenamiento S3
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
from datetime import date, datetime, timezone

from db.database import init_db, SessionLocal
from db.crud import (
    list_projects, count_projects,
    list_all_files,
)

# ── Inicializar BD al arrancar ────────────────────────────────────────────────
init_db()

# ── Configuración de página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Cuadros de Carga — Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Estilos ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .block-container{padding-top:1.2rem;}
  .metric-card{
    background:#1F3864;color:white;border-radius:10px;
    padding:14px 20px;text-align:center;
  }
  .metric-card h2{font-size:2rem;margin:0;color:white;}
  .metric-card p{font-size:.82rem;margin:0;opacity:.85;}
  .project-card{
    background:white;border:1px solid #D6E4F0;border-radius:8px;
    padding:12px 16px;margin:4px 0;
  }
  .project-card:hover{border-color:#1F3864;box-shadow:0 2px 8px rgba(31,56,100,.12);}
  .badge-active{background:#C6EFCE;color:#375623;border-radius:4px;
    padding:2px 8px;font-size:.75rem;font-weight:700;}
  .badge-archived{background:#F2F2F2;color:#666;border-radius:4px;
    padding:2px 8px;font-size:.75rem;font-weight:700;}
  .sec-hdr{background:#1F3864;color:white;border-radius:6px;
    padding:5px 12px;margin:10px 0 4px 0;font-weight:700;font-size:.88rem;}
  h1{color:#1F3864;}
  a{color:#1F3864;}
</style>
""", unsafe_allow_html=True)


# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 8])
with col_title:
    st.title("⚡ Cuadros de Carga — Alumbrado Público Vial")
    st.caption("Sistema de gestión de proyectos eléctricos · Normativa SEC Chile · RIC / Manual Carreteras MOP")

st.markdown("---")

# ── Métricas generales ────────────────────────────────────────────────────────
db = SessionLocal()
try:
    n_activos   = count_projects(db, status="activo")
    n_archivados = count_projects(db, status="archivado")
    all_files   = list_all_files(db, limit=1000)
    n_pdf       = sum(1 for f in all_files if f.file_type == "pdf")
    n_xlsx      = sum(1 for f in all_files if f.file_type == "xlsx")
    size_total  = sum(f.file_size_kb for f in all_files)
finally:
    db.close()

m1, m2, m3, m4, m5 = st.columns(5)

def _metric_card(col, title, value, subtitle=""):
    col.markdown(
        f'<div class="metric-card"><h2>{value}</h2><p>{title}</p>'
        f'{"<p style=opacity:.7;font-size:.72rem>"+subtitle+"</p>" if subtitle else ""}</div>',
        unsafe_allow_html=True,
    )

_metric_card(m1, "Proyectos activos",    n_activos)
_metric_card(m2, "Proyectos archivados", n_archivados)
_metric_card(m3, "PDFs generados",       n_pdf)
_metric_card(m4, "Excels generados",     n_xlsx)
_metric_card(m5, "Almacenamiento",       f"{size_total/1024:.1f} MB" if size_total > 1024 else f"{size_total:.0f} KB")

st.markdown("<br>", unsafe_allow_html=True)

# ── Proyectos recientes ───────────────────────────────────────────────────────
col_left, col_right = st.columns([3, 1])

with col_left:
    st.markdown('<div class="sec-hdr">📋 Proyectos Recientes</div>', unsafe_allow_html=True)

    db = SessionLocal()
    try:
        proyectos = list_projects(db, status="activo", limit=10)
    finally:
        db.close()

    if not proyectos:
        st.info("No hay proyectos activos. Ve a **📋 Proyectos** para crear el primero.")
    else:
        for p in proyectos:
            data   = p.get_data()
            n_emp  = len(data.get("empalmes", []))
            upd    = p.updated_at
            if upd and upd.tzinfo:
                upd_str = upd.strftime("%d/%m/%Y %H:%M")
            else:
                upd_str = str(upd)[:16] if upd else "—"

            c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
            with c1:
                st.markdown(
                    f"**{p.name}** &nbsp; "
                    f'<span class="badge-active">activo</span>',
                    unsafe_allow_html=True,
                )
                st.caption(f"Tramo: {p.tramo}  |  DM {p.dm_ini} – {p.dm_fin}  |  Ing.: {p.ingeniero}")
            with c2:
                st.caption(f"🔌 {n_emp} empalme{'s' if n_emp != 1 else ''}")
            with c3:
                st.caption(f"🕐 {upd_str}")
            with c4:
                # Botón de acceso directo al cálculo
                if st.button("Abrir", key=f"open_{p.id}", use_container_width=True):
                    st.session_state["active_project_id"]   = p.id
                    st.session_state["active_project_name"] = p.name
                    st.switch_page("pages/2_⚡_Cálculo.py")
            st.divider()

with col_right:
    st.markdown('<div class="sec-hdr">⚡ Accesos Rápidos</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("➕ Nuevo Proyecto", use_container_width=True, type="primary"):
        st.switch_page("pages/1_📋_Proyectos.py")

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("📋 Gestionar Proyectos", use_container_width=True):
        st.switch_page("pages/1_📋_Proyectos.py")

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("📁 Ver Archivos Generados", use_container_width=True):
        st.switch_page("pages/3_📁_Archivos.py")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Normativa aplicada:**")
    st.markdown("""
- SEC RIC-N6 / RIC-10
- IEC 60364-4-43 (Icc)
- Manual Carreteras MOP
- FP=0.95 | ΔV≤3%
- Desb.≤10%
""")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    f"⚡ Cuadros de Carga Platform v2.0 · "
    f"SEC RIC / Manual Carreteras MOP · "
    f"Hoy: {date.today().strftime('%d/%m/%Y')}"
)
