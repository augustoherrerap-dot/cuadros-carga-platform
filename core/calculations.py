"""
Motor de cálculos eléctricos normativos SEC Chile
Alumbrado Público Vial — RIC / Manual Carreteras MOP
Selección de conductor por tres criterios:
  1. Capacidad de corriente (ampacidad)
  2. Caída de tensión (ΔV ≤ 3%)
  3. Capacidad de cortocircuito (adiabática IEC 60364-4-43)
"""
import math

# ── Constantes normativas ─────────────────────────────────────────────────────
V_1F = 220.0
V_3F = 380.0
V_FASE_3F = V_3F / math.sqrt(3)   # ≈ 219.4 V (tensión de fase)
FP_DEFAULT = 0.95
FS = 1.0
F_DISENO = 1.25
COND_AL = 38.0                     # Conductividad Al [m/(Ω·mm²)]
COND_CU = 56.0                     # Conductividad Cu [m/(Ω·mm²)]
DV_MAX = 3.0                       # Caída máxima recomendada [%]
DESBALANCE_MAX = 10.0              # Desbalance máximo [%]

# Factor adiabático k [A·s⁰·⁵/mm²] — IEC 60364-4-43 / Tabla 43A
# Temperatura inicial: 90°C (XLPE) / 70°C (PVC) → final: 250°C (XLPE) / 160°C (PVC)
K_CONDUCTOR = {
    "CU": {"XLPE": 143, "PVC": 115},
    "AL": {"XLPE":  94, "PVC":  74},
}

# Disyuntores estándar [A]
DISYUNTORES = [6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400]

# Conductores con ampacidad [mm², A] — cables XLPE en conduit, 40°C ambiente
# Fuente: IEC 60364-5-52 / Tablas SEC Chile
CONDUCTORES_AL = [
    (2.5, 18.5), (4, 25), (6, 32), (10, 44), (16, 59),
    (25, 77), (35, 96), (50, 117), (70, 150), (95, 183), (120, 210),
]
CONDUCTORES_CU = [
    (2.5, 24), (4, 32), (6, 41), (10, 57), (16, 76),
    (25, 101), (35, 125), (50, 151), (70, 192), (95, 232), (120, 269),
]

SECCIONES_STD = sorted(set(
    [s for s, _ in CONDUCTORES_AL] + [s for s, _ in CONDUCTORES_CU]
))

ESCENARIOS_DIMERIZACION = [
    {"nombre": "Punta (100%)",      "factor": 1.00},
    {"nombre": "Media noche (70%)", "factor": 0.70},
    {"nombre": "Valle (50%)",       "factor": 0.50},
]

FASE_CICLO_3F = ["R", "S", "T"]


# ── Funciones base ─────────────────────────────────────────────────────────────

def calc_corriente_diseno(corriente_a: float) -> float:
    return round(corriente_a * F_DISENO, 3)


def seleccionar_disyuntor(corriente_a: float) -> int:
    for c in DISYUNTORES:
        if c >= calc_corriente_diseno(corriente_a):
            return c
    return DISYUNTORES[-1]


def _tabla_conductores(material: str):
    return CONDUCTORES_AL if material.upper() == "AL" else CONDUCTORES_CU


def seleccionar_conductor(corriente_a: float, material: str = "AL") -> tuple:
    for sec, cap in _tabla_conductores(material):
        if cap >= corriente_a:
            return sec, cap
    return _tabla_conductores(material)[-1]


def _siguiente_seccion_estandar(s_min: float, material: str) -> tuple:
    """Sección estándar inmediatamente igual o superior a s_min."""
    for sec, cap in _tabla_conductores(material):
        if sec >= s_min:
            return sec, cap
    return _tabla_conductores(material)[-1]


def escenarios_dimerizacion(potencia_kw: float, corriente_a: float) -> list:
    return [{
        "escenario": e["nombre"],
        "factor_pct": int(e["factor"] * 100),
        "potencia_kw": round(potencia_kw * e["factor"], 4),
        "corriente_a":  round(corriente_a * e["factor"], 3),
    } for e in ESCENARIOS_DIMERIZACION]


# ── Selección de conductor por tres criterios ──────────────────────────────────

def seleccionar_conductor_completo(
    i_calc: float,
    postes: list,
    tipo_empalme: str,
    fp: float = FP_DEFAULT,
    material: str = "AL",
    tipo_aislamiento: str = "XLPE",
    i_cc: float = 1500.0,
    t_prot: float = 0.40,
    seccion_override: float = None,
) -> dict:
    """
    Selecciona la sección de conductor satisfaciendo los tres criterios normativos:
      1. Capacidad de corriente (ampacidad ≥ I_diseño)
      2. Caída de tensión (ΔV ≤ 3% — cálculo directo inverso)
      3. Capacidad de cortocircuito (IEC 60364-4-43: S ≥ Icc·√t / k)

    Retorna dict con sección seleccionada, mínimos por criterio y criterio limitante.
    """
    sigma = COND_AL if material.upper() == "AL" else COND_CU
    k = K_CONDUCTOR.get(material.upper(), K_CONDUCTOR["AL"]).get(
            tipo_aislamiento.upper(), 94)

    # ── Criterio 1: Capacidad de corriente ────────────────────────────────────
    i_diseno = calc_corriente_diseno(i_calc)
    s1, cap1 = seleccionar_conductor(i_diseno, material)

    # ── Criterio 2: Caída de tensión (directo) ────────────────────────────────
    # 1F: S_min = 2·Σ(d_j·I_seg_j) / (σ·ΔV_max_V)
    # 3F: S_min = Σ(d_j·I_seg_fase_j)_max_fase / (σ·ΔV_max_V_fase)
    if tipo_empalme == "1F":
        dv_ref = V_1F * DV_MAX / 100        # 6.60 V
        f_dv = sum(2 * p["interdistancia_m"] * p["i_segmento_a"]
                   for p in postes)
    else:
        dv_ref = V_FASE_3F * DV_MAX / 100   # ≈ 6.58 V
        acum = {"R": 0.0, "S": 0.0, "T": 0.0}
        for p in postes:
            f = p.get("fase", "R")
            if f in acum:
                acum[f] += p["interdistancia_m"] * p["i_segmento_a"]
        f_dv = max(acum.values())

    s2_min = f_dv / (sigma * dv_ref) if dv_ref > 0 else 0.0
    s2, cap2 = _siguiente_seccion_estandar(s2_min, material)

    # ── Criterio 3: Capacidad de cortocircuito ────────────────────────────────
    # S_min [mm²] = Icc [A] · √t [s] / k
    s3_min = (i_cc * math.sqrt(t_prot)) / k
    s3, cap3 = _siguiente_seccion_estandar(s3_min, material)

    # ── Sección final ─────────────────────────────────────────────────────────
    if seccion_override and seccion_override > 0:
        s_final = float(seccion_override)
        cap_final = next(
            (cap for sec, cap in _tabla_conductores(material) if sec == s_final),
            cap3,
        )
        criterio = "Manual (override)"
    else:
        s_final = max(s1, s2, s3)
        # Criterio limitante: el que exige la mayor sección
        if s3 >= s2 and s3 >= s1:
            criterio = "Cortocircuito"
        elif s2 >= s1:
            criterio = "Caída de tensión"
        else:
            criterio = "Capacidad de corriente"
        cap_final = next(
            (cap for sec, cap in _tabla_conductores(material) if sec == s_final),
            cap3,
        )

    # Corriente de cortocircuito admisible del conductor seleccionado
    i_cc_adm = round(k * s_final / math.sqrt(t_prot), 1) if t_prot > 0 else 0.0

    # ΔV calculada con la sección final (para verificación)
    if tipo_empalme == "1F":
        dv_verificacion_v   = round(f_dv / (sigma * s_final), 4) if s_final > 0 else 0
        dv_verificacion_pct = round((dv_verificacion_v / V_1F) * 100, 3)
    else:
        dv_verificacion_v   = round(f_dv / (sigma * s_final), 4) if s_final > 0 else 0
        dv_verificacion_pct = round((dv_verificacion_v / V_FASE_3F) * 100, 3)

    return {
        # Por criterio
        "s_por_corriente_mm2": s1,
        "cap_corriente_a":     cap1,
        "s_por_dv_mm2":        s2,
        "s_dv_min_calc":       round(s2_min, 4),
        "s_por_cc_mm2":        s3,
        "s_cc_min_calc":       round(s3_min, 4),
        "i_cc_entrada":        i_cc,
        "t_prot_s":            t_prot,
        "k_adiab":             k,
        "tipo_aislamiento":    tipo_aislamiento,
        # Selección
        "seccion_mm2":         s_final,
        "capacidad_a":         cap_final,
        "criterio_limitante":  criterio,
        "i_cc_admisible_a":    i_cc_adm,
        "cumple_corriente":    cap_final >= i_diseno,
        "cumple_dv":           dv_verificacion_pct <= DV_MAX,
        "cumple_cc":           i_cc_adm >= i_cc,
        "dv_verificacion_pct": dv_verificacion_pct,
    }


# ── Cálculo detallado poste a poste ──────────────────────────────────────────

def calcular_circuito_detallado(
    id_empalme_num: int,
    id_circuito: int,
    tipo_empalme: str,
    postes_input: list,
    fp: float = FP_DEFAULT,
    material: str = "AL",
    tipo_aislamiento: str = "XLPE",
    i_cc: float = 1500.0,
    t_prot: float = 0.40,
    seccion_override: float = None,
    farthest_first: bool = False,
) -> dict:
    """
    Cálculo completo de un circuito con:
    - Potencias e interdistancias variables por poste
    - Fases alternas R/S/T (3F)
    - Código luminaria automático (EE.CC.NN)
    - Selección de conductor por 3 criterios normtivos
    """
    if not postes_input:
        return {}

    # Cuando farthest_first=True el orden en postes_input es:
    #   postes_input[0] = luminaria MÁS ALEJADA del empalme (lum 1)
    #   postes_input[-1] = luminaria MÁS CERCANA al empalme (lum N)
    # El motor eléctrico requiere el orden inverso (cercana primero),
    # ya que i_segmento[i] = Σ I[i:] asume postes[0] = más cercana.
    # Invertimos antes de calcular y volvemos a invertir al final para display.
    if farthest_first:
        postes_input = list(reversed(postes_input))

    sigma = COND_AL if material.upper() == "AL" else COND_CU
    n = len(postes_input)

    # ── 1. Construir postes con fase y corriente individual ───────────────────
    postes = []
    for i, p in enumerate(postes_input):
        post = {
            "numero":          i + 1,
            # Usar código del input si existe (p.ej. importado de Excel)
            "codigo":          p.get("codigo") or f"{id_empalme_num:02d}.{id_circuito:02d}.{i+1:02d}",
            "interdistancia_m": float(p.get("interdistancia_m", 35.0)),
            "pot_w":            float(p.get("pot_w", 133.0)),
        }
        if tipo_empalme == "3F":
            f_raw = str(p.get("fase", "")).strip().upper()
            post["fase"] = f_raw if f_raw in FASE_CICLO_3F else FASE_CICLO_3F[i % 3]
            post["corriente_a"] = round(
                post["pot_w"] / (math.sqrt(3) * V_3F * fp), 5)
        else:
            post["fase"] = "—"
            post["corriente_a"] = round(post["pot_w"] / (V_1F * fp), 5)
        postes.append(post)

    # ── 2. Corriente por fase (3F) ─────────────────────────────────────────────
    i_por_fase = {"R": 0.0, "S": 0.0, "T": 0.0}
    for p in postes:
        if p["fase"] in i_por_fase:
            i_por_fase[p["fase"]] += p["corriente_a"]

    if tipo_empalme == "3F":
        i_total = round(max(i_por_fase.values()), 5)   # Peor fase
        i_total_sum = round(sum(p["corriente_a"] for p in postes), 5)
    else:
        i_total = round(sum(p["corriente_a"] for p in postes), 5)
        i_total_sum = i_total

    # ── 3. Corrientes de segmento (independientes de la sección) ──────────────
    if tipo_empalme == "1F":
        for i in range(n):
            postes[i]["i_segmento_a"] = round(
                sum(p["corriente_a"] for p in postes[i:]), 5)
    else:
        for i in range(n):
            fase_i = postes[i]["fase"]
            postes[i]["i_segmento_a"] = round(
                sum(p["corriente_a"] for p in postes[i:]
                    if p["fase"] == fase_i), 5)

    # ── 4. Selección de conductor por tres criterios ───────────────────────────
    cond = seleccionar_conductor_completo(
        i_calc=i_total,
        postes=postes,
        tipo_empalme=tipo_empalme,
        fp=fp,
        material=material,
        tipo_aislamiento=tipo_aislamiento,
        i_cc=i_cc,
        t_prot=t_prot,
        seccion_override=seccion_override,
    )
    seccion = cond["seccion_mm2"]
    capacidad = cond["capacidad_a"]

    # ── 5. Caída de tensión poste a poste con sección final ───────────────────
    if tipo_empalme == "1F":
        dv_acum = 0.0
        for p in postes:
            dv_t = (2 * p["interdistancia_m"] * p["i_segmento_a"]) / (sigma * seccion)
            p["dv_tramo_v"]   = round(dv_t, 5)
            dv_acum          += dv_t
            p["dv_acum_v"]    = round(dv_acum, 5)
            p["dv_acum_pct"]  = round((dv_acum / V_1F) * 100, 4)
    else:
        dv_acum_fase = {"R": 0.0, "S": 0.0, "T": 0.0}
        for p in postes:
            f = p["fase"]
            dv_t = (p["interdistancia_m"] * p["i_segmento_a"]) / (sigma * seccion)
            p["dv_tramo_v"]  = round(dv_t, 5)
            dv_acum_fase[f] += dv_t
            p["dv_acum_v"]   = round(dv_acum_fase[f], 5)
            p["dv_acum_pct"] = round((dv_acum_fase[f] / V_FASE_3F) * 100, 4)

    # ── 6. Revertir postes al orden original si farthest_first ───────────────
    # Esto permite que el display muestre lum 1 (más alejada) primero.
    if farthest_first:
        postes = list(reversed(postes))

    # ── 7. Estadísticas del circuito ───────────────────────────────────────────
    pot_total_kw = round(sum(p["pot_w"] for p in postes) / 1000.0, 5)
    dv_max_pct   = max(p["dv_acum_pct"] for p in postes)
    dv_max_v     = max(p["dv_acum_v"]   for p in postes)

    i_diseno = calc_corriente_diseno(i_total)
    disyuntor = seleccionar_disyuntor(i_total)
    tension   = V_3F if tipo_empalme == "3F" else V_1F

    # Resumen por fase
    fase_data = {}
    if tipo_empalme == "3F":
        for f in ["R", "S", "T"]:
            fps = [p for p in postes if p["fase"] == f]
            fase_data[f] = {
                "n_luminarias": len(fps),
                "pot_kw":       round(sum(p["pot_w"] for p in fps) / 1000, 5),
                "corriente_a":  round(sum(p["corriente_a"] for p in fps), 4),
            }
    else:
        fase_data["—"] = {
            "n_luminarias": n,
            "pot_kw":       pot_total_kw,
            "corriente_a":  round(i_total, 4),
        }

    return {
        "circuito":            id_circuito,
        "fase":                "R/S/T" if tipo_empalme == "3F" else "—",
        "n_luminarias":        n,
        "pot_instalada_kw":    round(pot_total_kw, 4),
        "fp":                  fp,
        "tension_v":           tension,
        "corriente_calc_a":    round(i_total, 3),
        "corriente_total_a":   round(i_total_sum, 3),
        "corriente_diseno_a":  round(i_diseno, 3),
        "disyuntor_a":         disyuntor,
        "material":            material,
        "tipo_aislamiento":    tipo_aislamiento,
        "seccion_mm2":         seccion,
        "capacidad_conductor_a": capacidad,
        "longitud_m":          round(sum(p["interdistancia_m"] for p in postes), 1),
        "dv_v":                round(dv_max_v, 4),
        "dv_pct":              round(dv_max_pct, 3),
        "dimerizacion":        escenarios_dimerizacion(pot_total_kw, i_total),
        "cumple_dv":           dv_max_pct <= DV_MAX,
        "cumple_conductor":    i_total <= capacidad,
        "postes":              postes,
        "fase_data":           fase_data,
        "i_por_fase":          i_por_fase if tipo_empalme == "3F" else {},
        # Detalle selección conductor
        "conductor_seleccion": cond,
    }


# ── Balance de fases ──────────────────────────────────────────────────────────

def balance_fases_empalme(circuitos: list) -> dict:
    fases = {"R": 0.0, "S": 0.0, "T": 0.0}
    pot_f = {"R": 0.0, "S": 0.0, "T": 0.0}
    for c in circuitos:
        for f in ["R", "S", "T"]:
            fases[f] += c.get("i_por_fase", {}).get(f, 0.0)
            pot_f[f]  += c.get("fase_data", {}).get(f, {}).get("pot_kw", 0.0)

    i_list = list(fases.values())
    i_prom = sum(i_list) / 3 if sum(i_list) > 0 else 0

    result = {}
    for f in ["R", "S", "T"]:
        desb = round(abs(fases[f] - i_prom) / i_prom * 100, 2) if i_prom > 0 else 0.0
        result[f] = {
            "potencia_kw":   round(pot_f[f], 4),
            "corriente_a":   round(fases[f], 3),
            "desbalance_pct": desb,
        }

    max_d = max(v["desbalance_pct"] for v in result.values())
    return {
        "fases":              result,
        "i_promedio_a":       round(i_prom, 3),
        "desbalance_max_pct": round(max_d, 2),
        "cumple":             max_d <= DESBALANCE_MAX,
    }


# ── Resumen de empalme ─────────────────────────────────────────────────────────

def calcular_empalme(id_empalme: str, tipo: str, circuitos: list) -> dict:
    pot_total_kw = round(sum(c["pot_instalada_kw"] for c in circuitos), 4)
    n_lum_total  = sum(c["n_luminarias"] for c in circuitos)

    if tipo == "3F":
        bal = balance_fases_empalme(circuitos)
        i_max_a = max(bal["fases"][f]["corriente_a"] for f in bal["fases"])
    else:
        bal = None
        i_max_a = sum(c["corriente_calc_a"] for c in circuitos)

    return {
        "id":                  id_empalme,
        "tipo":                tipo,
        "n_circuitos":         len(circuitos),
        "n_luminarias_total":  n_lum_total,
        "pot_instalada_kw":    pot_total_kw,
        "pot_maxima_kw":       pot_total_kw,
        "corriente_max_a":     round(i_max_a, 3),
        "corriente_total_a":   round(sum(c.get("corriente_total_a", c["corriente_calc_a"]) for c in circuitos), 3),
        "disyuntor_gral_a":    seleccionar_disyuntor(i_max_a),
        "balance_fases":       bal,
        "dimerizacion":        escenarios_dimerizacion(pot_total_kw, i_max_a),
        "circuitos":           circuitos,
    }
