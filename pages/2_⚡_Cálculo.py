"""
Página de Cálculo — Cuadros de Carga
Adaptación de la app original con persistencia en BD y almacenamiento S3
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from datetime import date

from db.database import init_db, SessionLocal
from db.crud import (
    get_project, list_projects, save_project_data,
    create_generated_file,
)
from storage.client import get_storage, StorageClient
from core.calculations import (
    calcular_circuito_detallado, calcular_empalme,
    V_1F, V_3F, FP_DEFAULT, DV_MAX, DESBALANCE_MAX, FASE_CICLO_3F,
    CONDUCTORES_AL, CONDUCTORES_CU, K_CONDUCTOR,
)
from core.pdf_generator import generar_pdf
from core.excel_generator import generar_excel

init_db()

# ── Configuración ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Cálculo — Cuadros de Carga",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .block-container{padding-top:1rem;padding-bottom:1rem;}
  .stTabs [data-baseweb="tab"]{background:#D6E4F0;border-radius:6px 6px 0 0;
    padding:5px 14px;font-weight:600;color:#1F3864;}
  .stTabs [aria-selected="true"]{background:#1F3864 !important;color:white !important;}
  .sec-hdr{background:#1F3864;color:white;border-radius:6px;
    padding:5px 12px;margin:10px 0 4px 0;font-weight:700;font-size:.88rem;}
  .sub-hdr{background:#2E5899;color:white;border-radius:4px;
    padding:3px 10px;margin:6px 0 3px 0;font-weight:600;font-size:.82rem;}
  .project-banner{background:#E8F4FD;border-left:4px solid #1F3864;border-radius:0 6px 6px 0;
    padding:8px 14px;margin-bottom:10px;}
  .alert-ok {background:#C6EFCE;border-left:4px solid #375623;border-radius:5px;
    padding:4px 9px;font-size:.82rem;}
  .alert-err{background:#FFC7CE;border-left:4px solid #9C0006;border-radius:5px;
    padding:4px 9px;font-size:.82rem;}
  .alert-warn{background:#FFEB9C;border-left:4px solid #9C6500;border-radius:5px;
    padding:4px 9px;font-size:.82rem;}
  h1{color:#1F3864;}
</style>
""", unsafe_allow_html=True)

# ── Constantes UI ─────────────────────────────────────────────────────────────
POT_OPCIONES  = [38.8, 42.5, 70.0, 100.0, 133.0, 150.0, 200.0, 250.0, "Personalizada"]
TIPOS_EMPALME = ["Monofásico (1F — 220V)", "Trifásico (3F — 380/220V)"]
AISLAMIENTOS  = ["XLPE", "PVC"]
SECCIONES_AL  = [s for s, _ in CONDUCTORES_AL]
SECCIONES_CU  = [s for s, _ in CONDUCTORES_CU]
CRITERIO_ICON = {
    "Capacidad de corriente": "🔵",
    "Caída de tensión":       "🟡",
    "Cortocircuito":          "🔴",
    "Manual (override)":      "⚙️",
}


# ── Helpers DataFrame postes ──────────────────────────────────────────────────

def _fase_auto(i, tipo):
    return FASE_CICLO_3F[i % 3] if tipo == "3F" else "—"

def _codigos(df, emp_num, cto_num):
    df = df.copy()
    df["Código"] = [f"{emp_num:02d}.{cto_num:02d}.{i+1:02d}" for i in range(len(df))]
    return df

def _crear_df(n, sep, pot, tipo, emp_num, cto_num):
    rows = [{"Código": f"{emp_num:02d}.{cto_num:02d}.{i+1:02d}",
             "Interdistancia (m)": sep,
             "Potencia (W)": pot,
             "Fase": _fase_auto(i, tipo)} for i in range(n)]
    return pd.DataFrame(rows)

def _resize_df(df, new_n, sep, pot, tipo, emp_num, cto_num):
    old_n = len(df)
    if new_n > old_n:
        extra = _crear_df(new_n - old_n, sep, pot, tipo, emp_num, cto_num)
        extra["Código"] = [f"{emp_num:02d}.{cto_num:02d}.{old_n+i+1:02d}" for i in range(len(extra))]
        extra["Fase"]   = [_fase_auto(old_n + i, tipo) for i in range(len(extra))]
        df = pd.concat([df, extra], ignore_index=True)
    else:
        df = df.iloc[:new_n].copy()
    return _codigos(df, emp_num, cto_num)

def _df_to_postes(df):
    return [{"interdistancia_m": float(r["Interdistancia (m)"]),
             "pot_w":            float(r["Potencia (W)"]),
             "fase":             str(r["Fase"]),
             "codigo":           str(r.get("Código", ""))} for _, r in df.iterrows()]

def _secciones_disp(material):
    return SECCIONES_CU if material == "CU" else SECCIONES_AL


# ── Importación desde Excel ───────────────────────────────────────────────────

def _cargar_excel_to_session(file_bytes: bytes, idx: int, tipo: str) -> tuple:
    """
    Parsea el Excel y carga los circuitos en session_state para el empalme idx.
    Formato esperado (sin fila de encabezado obligatoria):
      Col A: Código  (p.ej. 1.1.1  ó  01.01.01)
      Col B: Potencia 1  (W)
      Col C: Potencia 2  (W) — gancho doble   [opcional]
      Col D: Potencia 3  (W) — triple          [opcional]
      Col E: Interdistancia siguiente (m)
    Convención: Luminaria 1 = MÁS ALEJADA del empalme.
    Retorna (n_circuitos, [mensajes])
    """
    try:
        import openpyxl
        from io import BytesIO
    except ImportError:
        return 0, ["❌ openpyxl no disponible — contacta al administrador."]

    try:
        wb = openpyxl.load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb.active
    except Exception as e:
        return 0, [f"❌ No se pudo abrir el Excel: {e}"]

    circuits: dict = {}   # {cto_num: [{"lum_n", "pot_w", "interdistancia_m"}]}

    for row in ws.iter_rows(min_row=1, values_only=True):
        if not row or row[0] is None:
            continue
        codigo_raw = str(row[0]).strip().replace(",", ".")
        try:
            parts = codigo_raw.split(".")
            if len(parts) != 3:
                continue
            _emp_n, cto_n, lum_n = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
        except (ValueError, IndexError):
            continue

        p1 = float(row[1]) if len(row) > 1 and row[1] is not None else 0.0
        p2 = float(row[2]) if len(row) > 2 and row[2] is not None else 0.0
        p3 = float(row[3]) if len(row) > 3 and row[3] is not None else 0.0
        inter = float(row[4]) if len(row) > 4 and row[4] is not None else 35.0
        pot_total = p1 + p2 + p3
        if pot_total <= 0:
            continue

        if cto_n not in circuits:
            circuits[cto_n] = []
        circuits[cto_n].append({
            "lum_n":          lum_n,
            "pot_w":          pot_total,
            "interdistancia_m": inter,
        })

    if not circuits:
        return 0, ["⚠️ No se encontraron filas válidas. "
                   "Verifica que la Col A tenga códigos (p.ej. 1.1.1) "
                   "y la Col B tenga potencias > 0."]

    emp_num   = idx + 1
    cto_keys  = sorted(circuits.keys())
    n_ctos    = len(cto_keys)
    msgs      = []

    for ci, cto_n in enumerate(cto_keys):
        # Ordenar: lum_n ascendente → lum 1 (más alejada) al inicio
        lums = sorted(circuits[cto_n], key=lambda x: x["lum_n"])
        n = len(lums)
        rows = []
        for i, lum in enumerate(lums):
            rows.append({
                "Código":            f"{emp_num:02d}.{cto_n:02d}.{lum['lum_n']:02d}",
                "Interdistancia (m)": lum["interdistancia_m"],
                "Potencia (W)":       lum["pot_w"],
                "Fase":               _fase_auto(i, tipo),
            })
        key_df = f"df_{idx}_{ci}"
        st.session_state[key_df]            = pd.DataFrame(rows)
        st.session_state[f"nlum_{idx}_{ci}"] = n
        st.session_state[f"farthest_{idx}_{ci}"] = True
        msgs.append(f"✅ Cto.{cto_n:02d}: {n} luminarias — "
                    f"{sum(l['pot_w'] for l in lums):.0f} W totales")

    st.session_state[f"ncto_{idx}"] = n_ctos
    return n_ctos, msgs


# ── Gestión de proyecto activo ────────────────────────────────────────────────

def _project_banner():
    """Muestra el proyecto activo con opciones de guardar / cambiar."""
    pid  = st.session_state.get("active_project_id")
    pname = st.session_state.get("active_project_name", "")

    if pid:
        bc1, bc2, bc3, bc4 = st.columns([5, 1.5, 1.5, 1.5])
        bc1.markdown(
            f'<div class="project-banner">📂 Proyecto activo: <strong>#{pid} — {pname}</strong></div>',
            unsafe_allow_html=True,
        )
        if bc2.button("💾 Guardar", key="btn_save_top", use_container_width=True, type="primary"):
            _save_project_data()
        if bc3.button("📋 Proyectos", key="btn_proj_top", use_container_width=True):
            st.switch_page("pages/1_📋_Proyectos.py")
        if bc4.button("🔓 Cerrar", key="btn_close_top", use_container_width=True):
            st.session_state.pop("active_project_id", None)
            st.session_state.pop("active_project_name", None)
            st.rerun()
    else:
        bc1, bc2, bc3 = st.columns([5, 2, 2])
        bc1.warning("⚠️ Sin proyecto activo. Selecciona o crea uno para guardar los cálculos.")
        if bc2.button("📋 Ir a Proyectos", use_container_width=True, type="primary"):
            st.switch_page("pages/1_📋_Proyectos.py")
        # Selector rápido de proyecto
        db = SessionLocal()
        try:
            proyectos = list_projects(db, status="activo", limit=30)
        finally:
            db.close()
        if proyectos:
            opciones = {f"#{p.id} — {p.name}": p.id for p in proyectos}
            sel = bc3.selectbox("O cargar uno:", ["—"] + list(opciones.keys()),
                                label_visibility="collapsed")
            if sel != "—":
                pid_sel = opciones[sel]
                db = SessionLocal()
                try:
                    pobj = get_project(db, pid_sel)
                    if pobj:
                        st.session_state["active_project_id"]   = pobj.id
                        st.session_state["active_project_name"] = pobj.name
                        _load_project_data(pobj)
                finally:
                    db.close()
                st.rerun()


def _collect_current_data() -> dict:
    """Recolectar todos los datos actuales del session_state en un dict serializable."""
    n_emp = st.session_state.get("n_empalmes_calc", 1)
    empalmes_data = []
    for idx in range(n_emp):
        emp_num  = idx + 1
        n_ctos   = st.session_state.get(f"ncto_{idx}", 3)
        circuitos_data = []
        for ci in range(n_ctos):
            cto_num = ci + 1
            key_df  = f"df_{idx}_{ci}"
            df      = st.session_state.get(key_df, pd.DataFrame())
            postes  = _df_to_postes(df) if not df.empty else []
            circuitos_data.append({
                "cto_num":      cto_num,
                "material":     st.session_state.get(f"mat_{idx}_{ci}", "AL"),
                "fp":           float(st.session_state.get(f"fp_{idx}_{ci}", FP_DEFAULT)),
                "postes":       postes,
                "farthest_first": bool(st.session_state.get(f"farthest_{idx}_{ci}", False)),
            })
        empalmes_data.append({
            "emp_id":      st.session_state.get(f"eid_{idx}", f"E-{emp_num:02d}"),
            "tipo":        "3F" if "3F" in str(st.session_state.get(f"tipo_{idx}", "3F")) else "1F",
            "i_cc":        float(st.session_state.get(f"icc_{idx}", 1500.0)),
            "t_prot":      float(st.session_state.get(f"tprot_{idx}", 0.40)),
            "aislamiento": st.session_state.get(f"aisl_{idx}", "XLPE"),
            "n_ctos":      n_ctos,
            "circuitos":   circuitos_data,
        })

    nombre = st.session_state.get("nombre_proyecto_calc", "")
    return {
        "metadata": {
            "nombre":    nombre,
            "tramo":     st.session_state.get("tramo_calc", ""),
            "dm_ini":    st.session_state.get("dm_ini_calc", ""),
            "dm_fin":    st.session_state.get("dm_fin_calc", ""),
            "ingeniero": st.session_state.get("ingeniero_calc", ""),
            "fecha":     str(st.session_state.get("fecha_calc", date.today())),
        },
        "n_empalmes": n_emp,
        "empalmes":   empalmes_data,
    }


def _save_project_data():
    """Guardar datos actuales en la BD."""
    pid = st.session_state.get("active_project_id")
    if not pid:
        st.warning("Selecciona un proyecto activo antes de guardar.")
        return
    data = _collect_current_data()
    db = SessionLocal()
    try:
        save_project_data(db, pid, data)
        # También actualizar metadatos del proyecto
        from db.crud import update_project
        meta = data.get("metadata", {})
        update_project(db, pid,
            name=meta.get("nombre", "") or st.session_state.get("active_project_name", ""),
            tramo=meta.get("tramo", ""),
            dm_ini=meta.get("dm_ini", ""),
            dm_fin=meta.get("dm_fin", ""),
            ingeniero=meta.get("ingeniero", ""),
        )
        st.toast(f"✅ Proyecto guardado correctamente.", icon="💾")
    except Exception as e:
        st.error(f"Error al guardar: {e}")
    finally:
        db.close()


def _load_project_data(pobj):
    """Cargar datos del proyecto en session_state."""
    data = pobj.get_data()
    if not data:
        return

    meta = data.get("metadata", {})
    st.session_state["nombre_proyecto_calc"] = meta.get("nombre", pobj.name)
    st.session_state["tramo_calc"]    = meta.get("tramo", pobj.tramo or "")
    st.session_state["dm_ini_calc"]   = meta.get("dm_ini", pobj.dm_ini or "")
    st.session_state["dm_fin_calc"]   = meta.get("dm_fin", pobj.dm_fin or "")
    st.session_state["ingeniero_calc"] = meta.get("ingeniero", pobj.ingeniero or "")

    n_emp = data.get("n_empalmes", 1)
    st.session_state["n_empalmes_calc"] = n_emp

    for idx, emp in enumerate(data.get("empalmes", [])):
        emp_num = idx + 1
        st.session_state[f"eid_{idx}"]  = emp.get("emp_id", f"E-{emp_num:02d}")
        st.session_state[f"tipo_{idx}"] = (
            "Trifásico (3F — 380/220V)" if emp.get("tipo") == "3F"
            else "Monofásico (1F — 220V)"
        )
        st.session_state[f"ncto_{idx}"]   = emp.get("n_ctos", 3)
        st.session_state[f"icc_{idx}"]    = emp.get("i_cc", 1500.0)
        st.session_state[f"tprot_{idx}"]  = emp.get("t_prot", 0.40)
        st.session_state[f"aisl_{idx}"]   = emp.get("aislamiento", "XLPE")

        tipo = emp.get("tipo", "3F")
        for ci, cto in enumerate(emp.get("circuitos", [])):
            cto_num = ci + 1
            key_df  = f"df_{idx}_{ci}"
            st.session_state[f"mat_{idx}_{ci}"]     = cto.get("material", "AL")
            st.session_state[f"fp_{idx}_{ci}"]      = cto.get("fp", FP_DEFAULT)
            st.session_state[f"farthest_{idx}_{ci}"] = cto.get("farthest_first", False)
            postes = cto.get("postes", [])
            if postes:
                rows = [{
                    "Código":            p.get("codigo") or f"{emp_num:02d}.{cto_num:02d}.{i+1:02d}",
                    "Interdistancia (m)": p.get("interdistancia_m", 35.0),
                    "Potencia (W)":       p.get("pot_w", 133.0),
                    "Fase":               p.get("fase", _fase_auto(i, tipo)),
                } for i, p in enumerate(postes)]
                st.session_state[key_df]              = pd.DataFrame(rows)
                st.session_state[f"nlum_{idx}_{ci}"] = len(postes)


def _export_and_save(file_bytes: bytes, file_type: str, proyecto: dict,
                     empalmes_exp: list, suffix: str) -> bytes:
    """Subir archivo al storage y registrar en BD. Retorna los bytes para descarga."""
    pid = st.session_state.get("active_project_id")
    nombre_p = proyecto.get("nombre", "Proyecto").replace(" ", "_")
    ts = date.today().strftime("%Y%m%d")
    file_name = f"Cuadro_Cargas_{nombre_p}_{ts}.{suffix}"

    storage = get_storage()

    if pid:
        key  = StorageClient.build_key(pid, file_type, file_name)
        url  = storage.upload(key, file_bytes,
                              "application/pdf" if suffix == "pdf"
                              else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        size = round(len(file_bytes) / 1024, 2)
        db = SessionLocal()
        try:
            create_generated_file(db, pid, file_type, file_name,
                                  storage_key=key, storage_url=url,
                                  file_size_kb=size)
        except Exception:
            pass
        finally:
            db.close()

    return file_bytes


# ═════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚡ Cuadros de Carga")
    st.markdown("**Alumbrado Público Vial — Chile**")
    st.markdown("---")

    # Cargar datos del proyecto activo (si viene de la página de proyectos)
    pid_activo = st.session_state.get("active_project_id")
    if pid_activo and "nombre_proyecto_calc" not in st.session_state:
        db = SessionLocal()
        try:
            pobj = get_project(db, pid_activo)
            if pobj:
                _load_project_data(pobj)
        finally:
            db.close()

    st.markdown("### Datos del Proyecto")
    nombre_proyecto = st.text_input(
        "Nombre del Proyecto",
        value=st.session_state.get("nombre_proyecto_calc", "Ampliación Ruta 5"),
        key="nombre_proyecto_calc",
    )
    tramo = st.text_input(
        "Tramo / Ruta",
        value=st.session_state.get("tramo_calc", "V-A Ruta 5"),
        key="tramo_calc",
    )
    c1, c2 = st.columns(2)
    dm_ini = c1.text_input("DM Inicial", value=st.session_state.get("dm_ini_calc", ""), key="dm_ini_calc")
    dm_fin = c2.text_input("DM Final",   value=st.session_state.get("dm_fin_calc", ""), key="dm_fin_calc")
    ingeniero = st.text_input("Ingeniero Responsable",
                              value=st.session_state.get("ingeniero_calc", ""),
                              key="ingeniero_calc")
    fecha = st.date_input("Fecha", value=date.today(), key="fecha_calc")
    st.markdown("---")
    n_empalmes = st.number_input("Número de empalmes", 1, 20,
                                 value=st.session_state.get("n_empalmes_calc", 1),
                                 step=1, key="n_empalmes_calc")
    st.markdown("---")

    if st.button("💾 Guardar Proyecto", use_container_width=True, type="primary"):
        _save_project_data()

    st.markdown("---")
    st.markdown("""
**Normativa aplicada:**
- SEC RIC-N6 / RIC-10
- IEC 60364-4-43 (Icc conductor)
- Manual Carreteras MOP
- FP=0.95 | ΔV≤3% | Desb.≤10%

**Criterios conductor:**
- 🔵 Capacidad corriente
- 🟡 Caída de tensión
- 🔴 Cortocircuito (IEC)
""")

proyecto = {
    "nombre": nombre_proyecto, "tramo": tramo,
    "dm_ini": dm_ini, "dm_fin": dm_fin,
    "ingeniero": ingeniero, "fecha": str(fecha),
}

# ═════════════════════════════════════════════════════════════════════════════
# ÁREA PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════
st.title("⚡ Cuadros de Carga — Alumbrado Público Vial")
st.markdown(f"**{nombre_proyecto}** | Tramo: {tramo} | DM {dm_ini} – {dm_fin}")

# Banner de proyecto activo
_project_banner()
st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tabs = st.tabs([f"Empalme {i+1:02d}" for i in range(n_empalmes)] + ["📊 Resumen"])

# ═════════════════════════════════════════════════════════════════════════════
for idx in range(n_empalmes):
    emp_num = idx + 1
    with tabs[idx]:

        ca, cb, cc = st.columns([1.5, 2, 1])
        with ca:
            emp_id = st.text_input("ID Empalme", value=f"E-{emp_num:02d}", key=f"eid_{idx}")
        with cb:
            tipo_idx = 0 if st.session_state.get(f"tipo_{idx}", "").startswith("Monof") else 1
            tipo_label = st.selectbox("Tipo", TIPOS_EMPALME, index=tipo_idx, key=f"tipo_{idx}")
        with cc:
            n_ctos = st.number_input("N° circuitos", 1, 10,
                                     value=st.session_state.get(f"ncto_{idx}", 3),
                                     key=f"ncto_{idx}")

        tipo = "3F" if "3F" in tipo_label else "1F"

        # Parámetros de cortocircuito
        st.markdown(
            '<div class="sub-hdr">Parámetros de cortocircuito del empalme</div>',
            unsafe_allow_html=True,
        )
        p1, p2, p3 = st.columns(3)
        with p1:
            i_cc_emp = st.number_input(
                "Icc en empalme (A)",
                min_value=100.0, max_value=50000.0,
                value=float(st.session_state.get(f"icc_{idx}", 1500.0)),
                step=100.0, key=f"icc_{idx}",
                help="Corriente de cortocircuito máxima. Típico BT autopistas Chile: 500–3000 A.",
            )
        with p2:
            t_prot_emp = st.number_input(
                "Tiempo de despeje (s)",
                min_value=0.02, max_value=2.0,
                value=float(st.session_state.get(f"tprot_{idx}", 0.40)),
                step=0.01, key=f"tprot_{idx}",
                help="0.4 s: disyuntor convencional | 0.2 s: curva rápida | 0.1 s: instantáneo",
            )
        with p3:
            aisl_idx = AISLAMIENTOS.index(st.session_state.get(f"aisl_{idx}", "XLPE"))
            aislamiento_emp = st.selectbox(
                "Aislamiento conductor", AISLAMIENTOS,
                index=aisl_idx, key=f"aisl_{idx}",
                help="XLPE: k=143(Cu)/94(Al)  PVC: k=115(Cu)/74(Al) — IEC 60364-4-43",
            )

        # ── Importar desde Excel ──────────────────────────────────────────────
        with st.expander("📥 Importar luminarias desde Excel", expanded=False):
            st.markdown("""
**Formato de columnas (sin encabezado requerido):**

| Col A | Col B | Col C | Col D | Col E |
|---|---|---|---|---|
| Código `1.1.1` | P1 (W) | P2 (W) *gancho doble* | P3 (W) *triple* | Interdistancia (m) |

> 🔢 **Lum. 1 = más alejada** del empalme · Lum. N = más cercana
> 🔌 **Gancho doble/triple:** suma P1+P2+P3 automáticamente
> 🗂️ Múltiples circuitos (segundo dígito) se crean como pestañas separadas
""")
            xl_file = st.file_uploader(
                "Seleccionar archivo Excel (.xlsx)",
                type=["xlsx"], key=f"xl_uploader_{idx}",
                label_visibility="collapsed",
            )
            if xl_file is not None:
                if st.button(f"⬆️ Importar circuitos en Empalme {emp_num:02d}",
                             key=f"xl_btn_{idx}", type="primary"):
                    n_imp, msgs_imp = _cargar_excel_to_session(
                        xl_file.read(), idx, tipo)
                    if n_imp:
                        for m in msgs_imp:
                            st.success(m)
                        st.info(f"📋 Se cargaron {n_imp} circuito(s). "
                                "Ajusta el 'N° circuitos' si es necesario y presiona Calcular.")
                        st.rerun()
                    else:
                        for m in msgs_imp:
                            st.warning(m)

        # Indicar convención activa
        any_farthest = any(
            st.session_state.get(f"farthest_{idx}_{ci}", False)
            for ci in range(n_ctos)
        )
        if any_farthest:
            st.info("📌 **Convención Excel activa:** Lum.01 = más alejada del empalme  |  Lum.N = más cercana")

        # ── Circuitos ─────────────────────────────────────────────────────────
        for ci in range(n_ctos):
            cto_num = ci + 1
            key_df  = f"df_{idx}_{ci}"

            with st.expander(f"Circuito {cto_num:02d}", expanded=(ci == 0)):

                d1, d2, d3, d4, d5 = st.columns([1.5, 2, 1.5, 1.5, 1.5])
                with d1:
                    n_lum = st.number_input("N° luminarias", 1, 100, 20,
                                            key=f"nlum_{idx}_{ci}")
                with d2:
                    pot_sel = st.selectbox("Potencia por defecto (W)", POT_OPCIONES,
                                           index=4, key=f"potsel_{idx}_{ci}")
                    pot_def = (
                        st.number_input("Potencia custom (W)", 1.0, 1000.0, 133.0,
                                        key=f"potcust_{idx}_{ci}")
                        if pot_sel == "Personalizada" else float(pot_sel)
                    )
                with d3:
                    sep_def = st.number_input("Interdist. por defecto (m)",
                                              1.0, 500.0, 35.0, step=0.5,
                                              key=f"sep_{idx}_{ci}")
                with d4:
                    mat_idx = 0 if st.session_state.get(f"mat_{idx}_{ci}", "AL") == "AL" else 1
                    material = st.selectbox("Material conductor", ["AL", "CU"],
                                            index=mat_idx, key=f"mat_{idx}_{ci}")
                with d5:
                    fp = st.number_input("Factor de Potencia", 0.7, 1.0,
                                         float(st.session_state.get(f"fp_{idx}_{ci}", FP_DEFAULT)),
                                         0.01, key=f"fp_{idx}_{ci}")

                sc1, sc2 = st.columns([1, 2])
                with sc1:
                    modo_sec = st.radio(
                        "Sección conductor",
                        ["Automática (3 criterios)", "Manual (override)"],
                        horizontal=True, key=f"modsec_{idx}_{ci}",
                    )
                with sc2:
                    secciones = _secciones_disp(material)
                    if modo_sec == "Manual (override)":
                        sec_override = st.selectbox(
                            f"Sección {'Cu' if material=='CU' else 'Al'} (mm²)",
                            secciones, index=2, key=f"secov_{idx}_{ci}",
                        )
                    else:
                        sec_override = None
                        st.caption(
                            f"Selección automática {'Cu' if material=='CU' else 'Al'}/{aislamiento_emp}: "
                            f"corriente, ΔV≤3%, Icc={i_cc_emp:.0f}A t={t_prot_emp:.2f}s"
                        )

                # DataFrame de postes
                if key_df not in st.session_state:
                    st.session_state[key_df] = _crear_df(
                        n_lum, sep_def, pot_def, tipo, emp_num, cto_num)
                elif len(st.session_state[key_df]) != n_lum:
                    st.session_state[key_df] = _resize_df(
                        st.session_state[key_df], n_lum, sep_def, pot_def,
                        tipo, emp_num, cto_num)
                st.session_state[key_df] = _codigos(
                    st.session_state[key_df], emp_num, cto_num)

                col_cfg = {
                    "Código": st.column_config.TextColumn(
                        "Código", disabled=True, width="small"),
                    "Interdistancia (m)": st.column_config.NumberColumn(
                        "Interdist. (m)", min_value=0.5, max_value=500.0,
                        step=0.5, format="%.1f"),
                    "Potencia (W)": st.column_config.NumberColumn(
                        "Potencia (W)", min_value=1.0, max_value=2000.0,
                        step=0.5, format="%.1f"),
                }
                if tipo == "3F":
                    col_cfg["Fase"] = st.column_config.SelectboxColumn(
                        "Fase", options=["R", "S", "T"], required=True)
                else:
                    col_cfg["Fase"] = st.column_config.TextColumn(
                        "Fase", disabled=True, width="small")

                st.markdown(
                    f'<div class="sec-hdr">Tabla de Postes — Cto. {cto_num:02d} | '
                    f'{"Fases alternas R/S/T" if tipo == "3F" else "Monofásico 220V"}</div>',
                    unsafe_allow_html=True,
                )
                edited_df = st.data_editor(
                    st.session_state[key_df], key=f"editor_{idx}_{ci}",
                    use_container_width=True, num_rows="fixed",
                    column_config=col_cfg, hide_index=True,
                )
                st.session_state[key_df] = _codigos(edited_df, emp_num, cto_num)

        # ── Botón calcular ─────────────────────────────────────────────────────
        if st.button(f"▶ Calcular {emp_id}", key=f"calc_{idx}", type="primary"):
            st.session_state[f"done_{idx}"] = True

        # ── Resultados ─────────────────────────────────────────────────────────
        if st.session_state.get(f"done_{idx}", False):
            circuitos_res = []
            for ci in range(n_ctos):
                cto_num  = ci + 1
                key_df   = f"df_{idx}_{ci}"
                mat_k    = st.session_state.get(f"mat_{idx}_{ci}", "AL")
                fp_k     = float(st.session_state.get(f"fp_{idx}_{ci}", FP_DEFAULT))
                aisl_k   = st.session_state.get(f"aisl_{idx}", "XLPE")
                modo_k   = st.session_state.get(f"modsec_{idx}_{ci}", "Automática (3 criterios)")
                sec_ov_k = (st.session_state.get(f"secov_{idx}_{ci}", None)
                            if "Manual" in str(modo_k) else None)

                df_cto = st.session_state.get(key_df, pd.DataFrame())
                if df_cto.empty:
                    continue
                farthest_k = bool(st.session_state.get(f"farthest_{idx}_{ci}", False))
                res = calcular_circuito_detallado(
                    id_empalme_num=emp_num,
                    id_circuito=cto_num,
                    tipo_empalme=tipo,
                    postes_input=_df_to_postes(df_cto),
                    fp=fp_k,
                    material=mat_k,
                    tipo_aislamiento=aisl_k,
                    i_cc=i_cc_emp,
                    t_prot=t_prot_emp,
                    seccion_override=sec_ov_k,
                    farthest_first=farthest_k,
                )
                circuitos_res.append(res)

            if not circuitos_res:
                st.warning("Sin datos de circuitos.")
                continue

            emp_res = calcular_empalme(emp_id, tipo, circuitos_res)

            # Métricas
            st.markdown("---")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Luminarias totales", emp_res["n_luminarias_total"])
            m2.metric("Potencia instalada", f"{emp_res['pot_instalada_kw']:.3f} kW")
            m3.metric("I máx.", f"{emp_res['corriente_max_a']:.2f} A")
            m4.metric("Disyuntor gral.", f"{emp_res['disyuntor_gral_a']} A")
            m5.metric("Circuitos", emp_res["n_circuitos"])

            # Selección de conductores
            st.markdown(
                '<div class="sec-hdr">Selección de Conductores por Criterio Normativo</div>',
                unsafe_allow_html=True,
            )
            rows_cond = []
            for c in circuitos_res:
                cs   = c["conductor_seleccion"]
                icon = CRITERIO_ICON.get(cs["criterio_limitante"], "")
                rows_cond.append({
                    "Cto.":              c["circuito"],
                    "Mat./Aisl.":        f"{c['material']}/{c['tipo_aislamiento']}",
                    "k":                 cs["k_adiab"],
                    "S corriente(mm²)":  cs["s_por_corriente_mm2"],
                    "S ΔV(mm²)":         cs["s_por_dv_mm2"],
                    "S mín.ΔV":          f"{cs['s_dv_min_calc']:.2f}",
                    "S Icc(mm²)":        cs["s_por_cc_mm2"],
                    "S mín.Icc":         f"{cs['s_cc_min_calc']:.2f}",
                    "→ S final(mm²)":    cs["seccion_mm2"],
                    "Criterio":          f"{icon} {cs['criterio_limitante']}",
                    "Ampacidad(A)":      cs["capacidad_a"],
                    "Icc_adm.(A)":       cs["i_cc_admisible_a"],
                    "ΔV verif.(%)":      f"{cs['dv_verificacion_pct']:.3f}%",
                    "✔I":  "✅" if cs["cumple_corriente"] else "❌",
                    "✔ΔV": "✅" if cs["cumple_dv"]        else "❌",
                    "✔Icc":"✅" if cs["cumple_cc"]        else "❌",
                })
            st.dataframe(pd.DataFrame(rows_cond), use_container_width=True, hide_index=True)
            st.caption(
                f"📌 Icc={i_cc_emp:.0f}A | t={t_prot_emp:.2f}s | "
                f"Aisl.={aislamiento_emp} | "
                "🔵 corriente  🟡 ΔV  🔴 Icc IEC 60364-4-43"
            )

            # Detalle por circuito
            st.markdown('<div class="sec-hdr">Detalle por Circuito</div>',
                        unsafe_allow_html=True)
            for c in circuitos_res:
                cs     = c["conductor_seleccion"]
                ok_all = c["cumple_dv"] and c["cumple_conductor"]
                icon   = CRITERIO_ICON.get(cs["criterio_limitante"], "")
                with st.expander(
                    f"Cto. {c['circuito']:02d} — {c['n_luminarias']} lum. — "
                    f"{c['pot_instalada_kw']:.3f} kW — I={c['corriente_calc_a']:.2f}A — "
                    f"{cs['seccion_mm2']:.1f}mm² {c['material']} "
                    f"({icon} {cs['criterio_limitante']}) — "
                    f"ΔV={c['dv_pct']:.2f}% — {'✅' if ok_all else '⚠️'}",
                    expanded=True,
                ):
                    r1, r2, r3, r4, r5, r6 = st.columns(6)
                    r1.metric("Sección",      f"{cs['seccion_mm2']:.1f} mm²")
                    r2.metric("Ampacidad",    f"{cs['capacidad_a']} A")
                    r3.metric("I diseño",     f"{c['corriente_diseno_a']:.2f} A")
                    r4.metric("Icc_adm.",     f"{cs['i_cc_admisible_a']:.0f} A")
                    r5.metric("ΔV máx.",      f"{c['dv_pct']:.3f}%",
                              delta="OK" if c["cumple_dv"] else "REVISAR",
                              delta_color="off" if c["cumple_dv"] else "inverse")
                    r6.metric("Criterio",     cs["criterio_limitante"])

                    rows_p = [{
                        "Código":        p["codigo"],
                        "Interdist.(m)": p["interdistancia_m"],
                        "Potencia(W)":   p["pot_w"],
                        "Fase":          p["fase"],
                        "I_poste(A)":    p["corriente_a"],
                        "I_seg(A)":      p["i_segmento_a"],
                        "ΔV_tramo(V)":   p["dv_tramo_v"],
                        "ΔV_acum(V)":    p["dv_acum_v"],
                        "ΔV_acum(%)":    p["dv_acum_pct"],
                    } for p in c["postes"]]
                    st.dataframe(pd.DataFrame(rows_p), use_container_width=True,
                                 hide_index=True,
                                 column_config={
                                     "ΔV_acum(%)": st.column_config.ProgressColumn(
                                         "ΔV_acum(%)", min_value=0, max_value=5,
                                         format="%.3f%%"),
                                 })

            # Balance de fases 3F
            if tipo == "3F" and emp_res["balance_fases"]:
                st.markdown('<div class="sec-hdr">Balance de Fases</div>',
                            unsafe_allow_html=True)
                bal = emp_res["balance_fases"]
                rows_b = [{
                    "Fase":           f,
                    "Potencia (kW)":  f"{bal['fases'][f]['potencia_kw']:.3f}",
                    "Corriente (A)":  f"{bal['fases'][f]['corriente_a']:.2f}",
                    "% Desbalance":   f"{bal['fases'][f]['desbalance_pct']:.2f}%",
                    "Estado": "✅" if bal["fases"][f]["desbalance_pct"] <= DESBALANCE_MAX else "⚠️",
                } for f in ["R", "S", "T"]]
                rows_b.append({
                    "Fase": "PROM.",
                    "Potencia (kW)": "—",
                    "Corriente (A)": f"{bal['i_promedio_a']:.2f}",
                    "% Desbalance": f"Máx: {bal['desbalance_max_pct']:.2f}%",
                    "Estado": "✅" if bal["cumple"] else "⚠️",
                })
                st.dataframe(pd.DataFrame(rows_b), use_container_width=True, hide_index=True)
                msg = ("✅ Balance de fases OK (≤10%)" if bal["cumple"]
                       else f"⚠️ Desbalance {bal['desbalance_max_pct']:.2f}% > 10% — redistribuir fases")
                cls = "alert-ok" if bal["cumple"] else "alert-err"
                st.markdown(f'<div class="{cls}">{msg}</div>', unsafe_allow_html=True)

            # Alertas
            alerts = []
            for c in circuitos_res:
                cs = c["conductor_seleccion"]
                if not c["cumple_dv"]:
                    alerts.append(f"⚠️ Cto.{c['circuito']:02d}: ΔV={c['dv_pct']:.2f}% > {DV_MAX}%")
                if not c["cumple_conductor"]:
                    alerts.append(f"⚠️ Cto.{c['circuito']:02d}: I_calc > ampacidad conductor")
                if not cs["cumple_cc"]:
                    alerts.append(f"⚠️ Cto.{c['circuito']:02d}: Icc_adm={cs['i_cc_admisible_a']:.0f}A < Icc={i_cc_emp:.0f}A")
            if not alerts:
                st.markdown(
                    '<div class="alert-ok">✅ Todos los circuitos cumplen los tres criterios normativos</div>',
                    unsafe_allow_html=True,
                )
            else:
                for a in alerts:
                    st.markdown(f'<div class="alert-err">{a}</div>', unsafe_allow_html=True)

            st.session_state[f"result_{idx}"] = emp_res


# ═════════════════════════════════════════════════════════════════════════════
# RESUMEN GENERAL
# ═════════════════════════════════════════════════════════════════════════════
with tabs[-1]:
    st.markdown("## Resumen General del Proyecto")
    empalmes_exp = [
        st.session_state[f"result_{i}"]
        for i in range(n_empalmes)
        if f"result_{i}" in st.session_state
    ]

    if not empalmes_exp:
        st.info("Calcule al menos un empalme para ver el resumen.")
    else:
        tot_lum = sum(e["n_luminarias_total"] for e in empalmes_exp)
        tot_kw  = sum(e["pot_instalada_kw"]   for e in empalmes_exp)
        tot_cto = sum(e["n_circuitos"]         for e in empalmes_exp)

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Empalmes",         len(empalmes_exp))
        r2.metric("Circuitos",        tot_cto)
        r3.metric("Luminarias",       tot_lum)
        r4.metric("Potencia total",   f"{tot_kw:.3f} kW")

        # Resumen conductores
        st.markdown('<div class="sec-hdr">Resumen de Conductores por Circuito</div>',
                    unsafe_allow_html=True)
        rows_sc = []
        for e in empalmes_exp:
            for c in e["circuitos"]:
                cs   = c["conductor_seleccion"]
                icon = CRITERIO_ICON.get(cs["criterio_limitante"], "")
                rows_sc.append({
                    "Empalme":       e["id"],
                    "Cto.":          c["circuito"],
                    "Mat./Aisl.":    f"{c['material']}/{c['tipo_aislamiento']}",
                    "S corr.(mm²)":  cs["s_por_corriente_mm2"],
                    "S ΔV(mm²)":     cs["s_por_dv_mm2"],
                    "S Icc(mm²)":    cs["s_por_cc_mm2"],
                    "→ S final(mm²)": cs["seccion_mm2"],
                    "Criterio":      f"{icon} {cs['criterio_limitante']}",
                    "Ampacidad(A)":  cs["capacidad_a"],
                    "Icc_adm.(A)":   cs["i_cc_admisible_a"],
                    "ΔV(%)":         f"{c['dv_pct']:.3f}%",
                    "✔I":  "✅" if cs["cumple_corriente"] else "❌",
                    "✔ΔV": "✅" if cs["cumple_dv"]       else "❌",
                    "✔Icc":"✅" if cs["cumple_cc"]       else "❌",
                })
        st.dataframe(pd.DataFrame(rows_sc), use_container_width=True, hide_index=True)

        st.markdown('<div class="sec-hdr">Tabla Resumen por Empalme</div>',
                    unsafe_allow_html=True)
        rows_res = [{
            "Empalme":         e["id"],
            "Tipo":            e["tipo"],
            "N° Circ.":        e["n_circuitos"],
            "N° Lum.":         e["n_luminarias_total"],
            "P.Inst.(kW)":     f"{e['pot_instalada_kw']:.3f}",
            "P.Máx.(kW)":      f"{e['pot_maxima_kw']:.3f}",
            "I Máx.(A)":       f"{e['corriente_max_a']:.2f}",
            "Disyuntor G.(A)": e["disyuntor_gral_a"],
        } for e in empalmes_exp]
        st.dataframe(pd.DataFrame(rows_res), use_container_width=True, hide_index=True)

        # ── Exportar ──────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("### Exportar y Guardar")
        col_pdf, col_xlsx, col_save = st.columns(3)

        with col_pdf:
            if st.button("📄 Generar PDF", type="primary", use_container_width=True):
                with st.spinner("Generando PDF…"):
                    try:
                        pdf_b = generar_pdf(proyecto, empalmes_exp)
                        pdf_b = _export_and_save(pdf_b, "pdf", proyecto, empalmes_exp, "pdf")
                        nombre_f = f"Cuadro_Cargas_{nombre_proyecto.replace(' ','_')}.pdf"
                        st.download_button(
                            "⬇️ Descargar PDF", pdf_b, nombre_f,
                            "application/pdf", use_container_width=True,
                        )
                        st.success("PDF generado y guardado.")
                    except Exception as e:
                        st.error(f"Error PDF: {e}")

        with col_xlsx:
            if st.button("📊 Generar Excel", type="secondary", use_container_width=True):
                with st.spinner("Generando Excel…"):
                    try:
                        xlsx_b = generar_excel(proyecto, empalmes_exp)
                        xlsx_b = _export_and_save(xlsx_b, "xlsx", proyecto, empalmes_exp, "xlsx")
                        nombre_f = f"Cuadro_Cargas_{nombre_proyecto.replace(' ','_')}.xlsx"
                        st.download_button(
                            "⬇️ Descargar Excel", xlsx_b, nombre_f,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                        )
                        st.success("Excel generado y guardado.")
                    except Exception as e:
                        st.error(f"Error Excel: {e}")

        with col_save:
            if st.button("💾 Guardar Cálculos", use_container_width=True):
                _save_project_data()

        # Observaciones técnicas
        st.markdown("---")
        st.markdown("### Observaciones Técnicas")
        obs = []
        for e in empalmes_exp:
            for c in e["circuitos"]:
                cs = c["conductor_seleccion"]
                if not c["cumple_dv"]:
                    obs.append(f"⚠️ **{e['id']} Cto.{c['circuito']:02d}**: ΔV={c['dv_pct']:.2f}% > 3%")
                if not c["cumple_conductor"]:
                    obs.append(f"⚠️ **{e['id']} Cto.{c['circuito']:02d}**: I_calc supera ampacidad")
                if not cs["cumple_cc"]:
                    obs.append(f"⚠️ **{e['id']} Cto.{c['circuito']:02d}**: "
                               f"Icc_adm={cs['i_cc_admisible_a']:.0f}A < Icc={cs['i_cc_entrada']:.0f}A")
            if e["tipo"] == "3F" and e["balance_fases"] and not e["balance_fases"]["cumple"]:
                obs.append(f"⚠️ **{e['id']}**: Desbalance {e['balance_fases']['desbalance_max_pct']:.2f}% > 10%")

        if not obs:
            st.markdown(
                '<div class="alert-ok">✅ Sin observaciones. '
                'Todos los empalmes cumplen los criterios normativos SEC / IEC 60364-4-43.</div>',
                unsafe_allow_html=True,
            )
        else:
            for o in obs:
                st.warning(o)

        with st.expander("💡 Oportunidades de Reducción Energética"):
            st.markdown(f"""
| Escenario | Factor | Potencia (kW) | Ahorro (kW) | Ahorro anual est. |
|---|---|---|---|---|
| Punta (100%) | 1.00 | {tot_kw:.3f} | 0 | — |
| Media noche (70%) | 0.70 | {tot_kw*0.70:.3f} | {tot_kw*0.30:.3f} | ≈ {tot_kw*0.30*4*365:.0f} kWh/año |
| Valle (50%) | 0.50 | {tot_kw*0.50:.3f} | {tot_kw*0.50:.3f} | ≈ {tot_kw*0.50*2*365:.0f} kWh/año |

*Estimado: media noche ≈ 4h/noche · valle ≈ 2h/noche*
""")
