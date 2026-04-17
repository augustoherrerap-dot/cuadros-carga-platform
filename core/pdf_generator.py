"""
Generador de PDF profesional — Cuadros de Carga Alumbrado Público
ReportLab — formato A4/Landscape
Incluye: detalle poste a poste, códigos luminaria, fases alternas
"""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph,
    Spacer, Table, TableStyle, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# ── Paleta ─────────────────────────────────────────────────────────────────────
AZUL_H   = colors.HexColor("#1F3864")
AZUL_CL  = colors.HexColor("#D6E4F0")
GRIS_F   = colors.HexColor("#F2F2F2")
VERDE_OK = colors.HexColor("#C6EFCE")
ROJO_NOK = colors.HexColor("#FFC7CE")
AMARILLO = colors.HexColor("#FFEB9C")
BLANCO   = colors.white
NEGRO    = colors.black

# Colores de fase
COL_R = colors.HexColor("#FFE0E0")
COL_S = colors.HexColor("#E0FFE0")
COL_T = colors.HexColor("#E0E8FF")

PAGE_W, PAGE_H = landscape(A4)
MARGIN = 14 * mm


def _estilos():
    ss = getSampleStyleSheet()
    titulo   = ParagraphStyle("titulo",    parent=ss["Heading1"], fontSize=12,
                               textColor=AZUL_H, spaceAfter=3, alignment=TA_CENTER)
    subtit   = ParagraphStyle("subtit",    parent=ss["Heading2"], fontSize=9,
                               textColor=AZUL_H, spaceAfter=2, alignment=TA_LEFT)
    normal   = ParagraphStyle("normal",    parent=ss["Normal"], fontSize=7.5, leading=10)
    nota     = ParagraphStyle("nota",      parent=ss["Normal"], fontSize=6.5,
                               textColor=colors.grey, leading=9)
    return {"titulo": titulo, "subtit": subtit, "normal": normal, "nota": nota}


def _ts_base():
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_H),
        ("TEXTCOLOR",     (0, 0), (-1, 0), BLANCO),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 6.5),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_F]),
        ("GRID",          (0, 0), (-1, -1), 0.25, colors.HexColor("#BBBBBB")),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
    ])


def _header_footer(canvas, doc, proyecto):
    canvas.saveState()
    w, h = doc.pagesize

    canvas.setFillColor(AZUL_H)
    canvas.rect(MARGIN, h - 18*mm, w - 2*MARGIN, 11*mm, fill=1, stroke=0)
    canvas.setFillColor(BLANCO)
    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.drawString(MARGIN + 3*mm, h - 11*mm,
                      proyecto.get("nombre", "CUADRO DE CARGAS — ALUMBRADO PÚBLICO"))
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(w - MARGIN - 3*mm, h - 11*mm,
                           f"Tramo: {proyecto.get('tramo','')}  "
                           f"DM {proyecto.get('dm_ini','')} – {proyecto.get('dm_fin','')}")

    canvas.setFillColor(AZUL_H)
    canvas.rect(MARGIN, 7*mm, w - 2*MARGIN, 5.5*mm, fill=1, stroke=0)
    canvas.setFillColor(BLANCO)
    canvas.setFont("Helvetica", 6)
    canvas.drawString(MARGIN + 3*mm, 9*mm,
                      f"Ing.: {proyecto.get('ingeniero','')}  |  "
                      f"Fecha: {proyecto.get('fecha', str(date.today()))}")
    canvas.drawCentredString(w / 2, 9*mm,
                             "Cálculos conforme SEC RIC-N6, RIC-10 y Manual Carreteras MOP")
    canvas.drawRightString(w - MARGIN - 3*mm, 9*mm, f"Pág. {doc.page}")
    canvas.restoreState()


# ── Tabla resumen circuitos ───────────────────────────────────────────────────
def _t_resumen_circuitos(emp):
    headers = ["Cto.", "Fases", "N° Lum.", "P.Inst.(kW)",
               "I calc.(A)", "I dis.(A)", "Disyuntor(A)",
               "Secc.(mm²)", "Long.(m)", "ΔV máx.(%)", "Estado"]
    cw = [12, 15, 14, 18, 18, 16, 18, 16, 14, 16, 18]
    cw = [x*mm for x in cw]

    rows = [headers]
    extra = []
    for i, c in enumerate(emp["circuitos"], start=1):
        ok = c["cumple_dv"] and c["cumple_conductor"]
        est = "CUMPLE" if ok else "REVISAR"
        fases_str = "/".join(sorted(set(
            p["fase"] for p in c.get("postes", []) if p["fase"] != "—"
        ))) or ("R/S/T" if emp["tipo"] == "3F" else "—")
        rows.append([
            str(c["circuito"]),
            fases_str,
            str(c["n_luminarias"]),
            f"{c['pot_instalada_kw']:.3f}",
            f"{c['corriente_calc_a']:.2f}",
            f"{c['corriente_diseno_a']:.2f}",
            str(c["disyuntor_a"]),
            f"{c['seccion_mm2']:.1f} {c['material']}",
            f"{c['longitud_m']:.0f}",
            f"{c['dv_pct']:.2f}%",
            est,
        ])
        extra.append(("BACKGROUND", (10, i), (10, i), VERDE_OK if ok else ROJO_NOK))
    # Totales
    rows.append([
        "TOTAL", "—", str(emp["n_luminarias_total"]), f"{emp['pot_instalada_kw']:.3f}",
        "—", "—", f"{emp['disyuntor_gral_a']}A", "—", "—", "—", "—",
    ])
    n = len(rows)
    extra += [
        ("BACKGROUND", (0, n-1), (-1, n-1), AZUL_CL),
        ("FONTNAME",   (0, n-1), (-1, n-1), "Helvetica-Bold"),
    ]
    ts = _ts_base()
    for s in extra:
        ts.add(*s)
    return Table(rows, colWidths=cw, style=ts, repeatRows=1)


# ── Tabla selección de conductor ─────────────────────────────────────────────
def _t_conductor(emp):
    """Tabla de selección de conductor por los tres criterios normativos."""
    headers = [
        "Cto.", "Mat./Aisl.", "k",
        "S corr.(mm²)", "S ΔV(mm²)", "S mín.ΔV", "S Icc(mm²)", "S mín.Icc",
        "→ S final(mm²)", "Criterio limitante",
        "Ampacidad(A)", "Icc_adm.(A)", "ΔV verif.(%)",
        "✔I", "✔ΔV", "✔Icc",
    ]
    cw = [10, 18, 9, 18, 16, 16, 16, 16, 18, 32, 18, 18, 16, 10, 10, 10]
    cw = [x*mm for x in cw]

    rows = [headers]
    extra = []
    for i, c in enumerate(emp["circuitos"], start=1):
        cs = c.get("conductor_seleccion", {})
        if not cs:
            continue
        ok_i = cs.get("cumple_corriente", True)
        ok_d = cs.get("cumple_dv", True)
        ok_c = cs.get("cumple_cc", True)
        rows.append([
            str(c["circuito"]),
            f"{c['material']}/{c.get('tipo_aislamiento','XLPE')}",
            str(cs.get("k_adiab", "—")),
            str(cs.get("s_por_corriente_mm2", "—")),
            str(cs.get("s_por_dv_mm2", "—")),
            f"{cs.get('s_dv_min_calc',0):.2f}",
            str(cs.get("s_por_cc_mm2", "—")),
            f"{cs.get('s_cc_min_calc',0):.2f}",
            str(cs.get("seccion_mm2", "—")),
            cs.get("criterio_limitante", "—"),
            str(cs.get("capacidad_a", "—")),
            f"{cs.get('i_cc_admisible_a',0):.0f}",
            f"{cs.get('dv_verificacion_pct',0):.3f}%",
            "SI" if ok_i else "NO",
            "SI" if ok_d else "NO",
            "SI" if ok_c else "NO",
        ])
        for col_idx, ok in [(13, ok_i), (14, ok_d), (15, ok_c)]:
            extra.append(("BACKGROUND", (col_idx, i), (col_idx, i),
                          VERDE_OK if ok else ROJO_NOK))
        extra.append(("BACKGROUND", (8, i), (8, i), AZUL_CL))
        extra.append(("FONTNAME",   (8, i), (8, i), "Helvetica-Bold"))

    ts = _ts_base()
    for s in extra:
        ts.add(*s)
    return Table(rows, colWidths=cw, style=ts, repeatRows=1)


# ── Tabla detalle poste a poste ───────────────────────────────────────────────
def _t_postes(circuito, emp_tipo):
    headers = ["Código", "Interdist.(m)", "Potencia(W)", "Fase",
               "I_poste(A)", "I_seg(A)", "ΔV_tramo(V)", "ΔV_acum(V)", "ΔV_acum(%)"]
    cw = [22, 18, 17, 12, 16, 16, 18, 18, 16]
    cw = [x*mm for x in cw]

    rows = [headers]
    extra = []
    FASE_COL = {"R": COL_R, "S": COL_S, "T": COL_T}

    for i, p in enumerate(circuito["postes"], start=1):
        dv_ok = p["dv_acum_pct"] <= 3.0
        rows.append([
            p["codigo"],
            f"{p['interdistancia_m']:.1f}",
            f"{p['pot_w']:.1f}",
            p["fase"],
            f"{p['corriente_a']:.4f}",
            f"{p['i_segmento_a']:.4f}",
            f"{p['dv_tramo_v']:.4f}",
            f"{p['dv_acum_v']:.4f}",
            f"{p['dv_acum_pct']:.3f}%",
        ])
        # Color por fase
        col_f = FASE_COL.get(p["fase"], BLANCO)
        extra.append(("BACKGROUND", (3, i), (3, i), col_f))
        # Color ΔV
        if not dv_ok:
            extra.append(("BACKGROUND", (8, i), (8, i), ROJO_NOK))

    # Fila de totales/máximos
    rows.append([
        "MÁX / TOTAL", "—",
        f"{sum(p['pot_w'] for p in circuito['postes']):.1f}",
        "—", "—", "—", "—",
        f"{max(p['dv_acum_v'] for p in circuito['postes']):.4f}",
        f"{circuito['dv_pct']:.3f}%",
    ])
    n = len(rows)
    extra += [
        ("BACKGROUND", (0, n-1), (-1, n-1), AZUL_CL),
        ("FONTNAME",   (0, n-1), (-1, n-1), "Helvetica-Bold"),
        ("BACKGROUND", (8, n-1), (8, n-1),
         VERDE_OK if circuito["cumple_dv"] else ROJO_NOK),
    ]
    ts = _ts_base()
    for s in extra:
        ts.add(*s)
    return Table(rows, colWidths=cw, style=ts, repeatRows=1)


# ── Tabla balance fases ───────────────────────────────────────────────────────
def _t_balance(bal):
    headers = ["Fase", "Potencia (kW)", "Corriente (A)", "% Desbalance", "Estado"]
    cw = [18, 30, 30, 30, 28]
    cw = [x*mm for x in cw]
    rows = [headers]
    extra = []
    for i, f in enumerate(["R", "S", "T"], start=1):
        fd = bal["fases"][f]
        ok = fd["desbalance_pct"] <= 10
        rows.append([f, f"{fd['potencia_kw']:.3f}", f"{fd['corriente_a']:.2f}",
                     f"{fd['desbalance_pct']:.2f}%", "CUMPLE" if ok else "REVISAR"])
        extra.append(("BACKGROUND", (4, i), (4, i), VERDE_OK if ok else ROJO_NOK))
    rows.append([
        "PROM.", "—", f"{bal['i_promedio_a']:.2f}",
        f"Máx: {bal['desbalance_max_pct']:.2f}%",
        "CUMPLE" if bal["cumple"] else "REVISAR",
    ])
    n = len(rows)
    extra += [
        ("BACKGROUND", (0, n-1), (-1, n-1), AZUL_CL),
        ("FONTNAME",   (0, n-1), (-1, n-1), "Helvetica-Bold"),
        ("BACKGROUND", (4, n-1), (4, n-1), VERDE_OK if bal["cumple"] else ROJO_NOK),
    ]
    ts = _ts_base()
    for s in extra:
        ts.add(*s)
    return Table(rows, colWidths=cw, style=ts, repeatRows=1)


# ── Tabla dimerización ────────────────────────────────────────────────────────
def _t_dimerizacion(dim):
    headers = ["Escenario", "% Potencia", "Potencia (kW)", "Corriente (A)"]
    cw = [50, 25, 30, 30]
    cw = [x*mm for x in cw]
    rows = [headers]
    bgs = [colors.HexColor("#E8F4FD"), GRIS_F, AMARILLO]
    for i, e in enumerate(dim):
        rows.append([e["escenario"], f"{e['factor_pct']}%",
                     f"{e['potencia_kw']:.3f}", f"{e['corriente_a']:.2f}"])
    ts = _ts_base()
    for i in range(1, len(rows)):
        ts.add("BACKGROUND", (0, i), (-1, i), bgs[(i-1) % 3])
    return Table(rows, colWidths=cw, style=ts, repeatRows=1)


# ── Tabla resumen general ─────────────────────────────────────────────────────
def _t_resumen_general(empalmes):
    headers = ["Empalme", "Tipo", "N° Circ.", "N° Lum.",
               "P.Inst.(kW)", "P.Máx.(kW)", "I Máx.(A)", "Disyuntor G.(A)"]
    cw = [22, 16, 18, 18, 25, 25, 20, 25]
    cw = [x*mm for x in cw]
    rows = [headers]
    for e in empalmes:
        rows.append([
            e["id"], e["tipo"], str(e["n_circuitos"]),
            str(e["n_luminarias_total"]),
            f"{e['pot_instalada_kw']:.3f}", f"{e['pot_maxima_kw']:.3f}",
            f"{e['corriente_max_a']:.2f}", str(e["disyuntor_gral_a"]),
        ])
    rows.append([
        "TOTAL PROYECTO", "—",
        str(sum(e["n_circuitos"] for e in empalmes)),
        str(sum(e["n_luminarias_total"] for e in empalmes)),
        f"{sum(e['pot_instalada_kw'] for e in empalmes):.3f}",
        f"{sum(e['pot_maxima_kw'] for e in empalmes):.3f}", "—", "—",
    ])
    n = len(rows)
    ts = _ts_base()
    ts.add("BACKGROUND", (0, n-1), (-1, n-1), AZUL_H)
    ts.add("TEXTCOLOR",  (0, n-1), (-1, n-1), BLANCO)
    ts.add("FONTNAME",   (0, n-1), (-1, n-1), "Helvetica-Bold")
    return Table(rows, colWidths=cw, style=ts, repeatRows=1)


# ── Tabla criterios normativos ────────────────────────────────────────────────
def _t_criterios():
    items = [
        ("SEC RIC-N6 Art. 7.3", "Diferencial 30mA alta sensibilidad: R_max = 50/0.03 Ω"),
        ("SEC RIC-N6 Art. 6.1", "Resistencia de seguridad: Rs = V/(2.5×I_max)"),
        ("SEC RIC-10 §5.1.4.1", "Capacidad adicional 10% en conductores"),
        ("Corriente de diseño",  "I_d = I_calc × 1.25 (factor seguridad SEC)"),
        ("Simultaneidad",        "FS = 1.0 — alumbrado público encendido simultáneamente"),
        ("Factor de potencia",   "FP = 0.95 — luminarias LED con driver electrónico"),
        ("Caída de tensión",     "ΔV ≤ 3% recomendado alumbrado vial (Manual Carreteras MOP)"),
        ("Balance de fases",     "Desbalance ≤ 10% sistemas trifásicos"),
        ("Dimerización",         "Escenarios: 100% punta / 70% media noche / 50% valle"),
        ("Fases alternas",       "Rotación R→S→T por poste en circuitos 3F (balanceo natural)"),
        ("Código luminaria",     "Formato: {empalme}.{circuito}.{luminaria} — Ej: 01.01.01"),
        ("ΔV 1F",                "ΔV = 2×Σ(d_j×I_seg_j) / (σ×S)   [ida y vuelta]"),
        ("ΔV 3F",                "ΔV_fase = Σ(d_j×I_seg_fase_j) / (σ×S)  [solo conductor de fase]"),
        ("Conductividad Al",     "σ = 38 m/(Ω·mm²)"),
        ("Conductividad Cu",     "σ = 56 m/(Ω·mm²)"),
    ]
    rows = [["Criterio / Normativa", "Descripción"]] + list(items)
    cw = [55*mm, 180*mm]
    ts = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_H),
        ("TEXTCOLOR",     (0, 0), (-1, 0), BLANCO),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME",      (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 6.5),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_F]),
        ("GRID",          (0, 0), (-1, -1), 0.25, colors.HexColor("#BBBBBB")),
        ("TOPPADDING",    (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ])
    return Table(rows, colWidths=cw, style=ts, repeatRows=1)


# ── Función principal ─────────────────────────────────────────────────────────
def generar_pdf(proyecto: dict, empalmes: list) -> bytes:
    buf = io.BytesIO()
    estilos = _estilos()

    def _hf(canvas, doc):
        _header_footer(canvas, doc, proyecto)

    doc = BaseDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=23*mm, bottomMargin=18*mm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=_hf)])

    S = estilos
    story = []

    # ── Portada / datos generales ─────────────────────────────────────────────
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("CUADRO DE CARGAS — ALUMBRADO PÚBLICO VIAL", S["titulo"]))
    story.append(Spacer(1, 2*mm))

    meta = [
        ["Proyecto:", proyecto.get("nombre","—"), "Tramo:", proyecto.get("tramo","—")],
        ["DM Inicial:", proyecto.get("dm_ini","—"), "DM Final:", proyecto.get("dm_fin","—")],
        ["Fecha:", proyecto.get("fecha", str(date.today())),
         "Ingeniero:", proyecto.get("ingeniero","—")],
        ["N° Empalmes:", str(len(empalmes)),
         "Total Luminarias:", str(sum(e["n_luminarias_total"] for e in empalmes))],
        ["Potencia Total:", f"{sum(e['pot_instalada_kw'] for e in empalmes):.3f} kW",
         "Normativa:", "SEC RIC / Manual Carreteras MOP"],
    ]
    meta_ts = TableStyle([
        ("FONTNAME",    (0,0),(0,-1), "Helvetica-Bold"),
        ("FONTNAME",    (2,0),(2,-1), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0),(-1,-1), 7.5),
        ("BACKGROUND",  (0,0),(-1,-1), AZUL_CL),
        ("GRID",        (0,0),(-1,-1), 0.25, colors.HexColor("#AAAAAA")),
        ("TOPPADDING",  (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
        ("LEFTPADDING", (0,0),(-1,-1), 5),
        ("RIGHTPADDING",(0,0),(-1,-1), 5),
        ("VALIGN",      (0,0),(-1,-1), "MIDDLE"),
    ])
    story.append(Table(meta, colWidths=[32*mm, 85*mm, 32*mm, 85*mm], style=meta_ts))
    story.append(Spacer(1, 4*mm))

    # Resumen general
    story.append(Paragraph("RESUMEN GENERAL DEL PROYECTO", S["subtit"]))
    story.append(Spacer(1, 1*mm))
    story.append(_t_resumen_general(empalmes))
    story.append(PageBreak())

    # ── Por empalme ───────────────────────────────────────────────────────────
    for emp in empalmes:
        story.append(Paragraph(
            f"EMPALME {emp['id']} — {emp['tipo']} — "
            f"{emp['n_luminarias_total']} lum. — {emp['pot_instalada_kw']:.3f} kW",
            S["subtit"],
        ))
        story.append(Spacer(1, 1*mm))

        # 1. Resumen de circuitos
        story.append(Paragraph("1. Resumen de Circuitos", S["normal"]))
        story.append(Spacer(1, 0.5*mm))
        story.append(_t_resumen_circuitos(emp))
        story.append(Spacer(1, 3*mm))

        # 2. Selección de conductor
        story.append(Paragraph("2. Selección de Conductor (corriente / ΔV / Icc — IEC 60364-4-43)", S["normal"]))
        story.append(Spacer(1, 0.5*mm))
        story.append(_t_conductor(emp))
        story.append(Spacer(1, 3*mm))

        # 3. Detalle poste a poste por circuito
        story.append(Paragraph("3. Detalle Poste a Poste por Circuito", S["normal"]))
        for c in emp["circuitos"]:
            story.append(Spacer(1, 1*mm))
            story.append(Paragraph(
                f"  Circuito {c['circuito']:02d} — {c['n_luminarias']} postes — "
                f"{c['pot_instalada_kw']:.3f} kW — "
                f"I={c['corriente_calc_a']:.2f}A — "
                f"Cond: {c['seccion_mm2']:.1f}mm² {c['material']}",
                S["nota"],
            ))
            story.append(Spacer(1, 0.5*mm))
            story.append(_t_postes(c, emp["tipo"]))
        story.append(Spacer(1, 3*mm))

        # 4. Balance de fases (3F)
        if emp["tipo"] == "3F" and emp["balance_fases"]:
            story.append(Paragraph("4. Balance de Fases", S["normal"]))
            story.append(Spacer(1, 0.5*mm))
            story.append(_t_balance(emp["balance_fases"]))
            story.append(Spacer(1, 3*mm))

        # 5. Dimerización
        sec = "5" if emp["tipo"] == "3F" else "4"
        story.append(Paragraph(f"{sec}. Escenarios de Dimerización", S["normal"]))
        story.append(Spacer(1, 0.5*mm))
        story.append(_t_dimerizacion(emp["dimerizacion"]))
        story.append(Spacer(1, 5*mm))

        story.append(PageBreak())

    # ── Criterios normativos ──────────────────────────────────────────────────
    story.append(Paragraph("CRITERIOS NORMATIVOS APLICADOS", S["subtit"]))
    story.append(Spacer(1, 1*mm))
    story.append(_t_criterios())

    doc.build(story)
    buf.seek(0)
    return buf.read()
