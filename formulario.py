# -*- coding: utf-8 -*-
# app.py — Formulario Comité de Riesgos (una sola hoja)
# - Desplegables de evaluación en TEXTO (no números)
# - Sin promedio de riesgo ni en PDF ni en la app
# - Interlineado mejorado + más espacio entre secciones en PDF
# - Resumen Ejecutivo con: Score, Calificación actual, Peor calificación
# - Instrucciones Generales (texto actualizado)
# - Parche para correr en Streamlit Cloud aunque falte reportlab (requirements.txt lo soluciona)

import io
from datetime import datetime
import streamlit as st

# ---- PDF (ReportLab) con fallback seguro ----
A4_FALLBACK = (595.2756, 841.8898)  # tamaño A4 en puntos (ancho, alto) por si falla el import

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib.utils import ImageReader
    PAGE_W, PAGE_H = A4
except Exception:
    # Si reportlab no está instalado, permitimos que la app cargue.
    canvas = None
    colors = None
    Table = None
    TableStyle = None
    ImageReader = None
    PAGE_W, PAGE_H = A4_FALLBACK
    # build_pdf() comprobará canvas is None y mostrará un error claro.

# Márgenes (usar 2cm; si cm no existe, aproximamos 2cm en puntos ≈ 56.69)
LM = 2 * (cm if 'cm' in globals() and cm else 28.3465)  # 56.693 pts
RM = LM
TM = LM
BM = LM
CONTENT_W = PAGE_W - LM - RM

# Ajustes de espaciado para el PDF
LINE_HEIGHT = 14          # interlineado
BLOCK_SPACE = 22          # espacio general después de bloques
TABLE_SPACE = 24          # espacio después de tablas
SECTION_EXTRA_GAP = 10    # respiro extra entre secciones

# ---- Texto guía: Instrucciones + Preguntas Orientadoras ----
INSTRUCCIONES = (
    "Este formulario debe ser completado por el analista antes de la sesión del Comité de Riesgos. "
    "Cada sección incluye una narrativa obligatoria sobre el criterio evaluado donde se comentarán "
    "puntos respecto a la pregunta orientadora dada. Además, se debe seleccionar una calificación "
    "según el grado de mitigación del riesgo identificado.\n"
    "Escala de evaluación: Crítico no mitigado, Alto con mitigación débil, Medio aceptable, Bien mitigado"
)

P_Q3 = ("Riesgos como ingresos no validados, concentración en un solo cliente, informalidad no mitigada, "
        "o problemas legales menores. ¿Están bien diagnosticados y mitigados?")
P_Q4 = ("¿Hay alineación entre ingresos, destino, monto, plazo, garantía, y tipo de cliente? "
        "¿Tiene sentido financiero y operativo?")
P_Q5 = ("¿Existen excepciones al scoring, LTV, score o historial? ¿Están explícitas, bien sustentadas "
        "y tienen lógica dentro del apetito de riesgo?")
P_Q6 = ("¿Hay fortalezas que compensan debilidades? Ej. garantía de calidad, destino productivo, cliente con "
        "experiencia sólida, historial positivo del cliente")
P_Q7 = ("¿Tiene referencias confiables? ¿Se conoce su comportamiento informal o trayectoria empresarial "
        "fuera de burós (historial crediticio)?")
P_Q8 = ("¿La operación encaja dentro de nuestra estrategia? ¿Es un cliente recurrente, bien gestionado, "
        "o clave para nuevas líneas?")
P_Q9 = ("¿Hay una fuente secundaria de repago clara o plan de salida en caso de stress? "
        "(venta de activo, refinanciamiento, otro flujo)")

# Opciones de evaluación (texto)
OPCIONES_EVAL = [
    "",
    "Crítico no mitigado",
    "Alto con mitigación débil",
    "Medio aceptable",
    "Bien mitigado",
]

# -------- Utilidades de maquetación PDF --------
def wrap_lines(text, font_name, font_size, max_w, canv):
    if not text:
        return ["-"]
    words = text.replace("\r", "").split()
    lines, line = [], ""
    for w in words:
        test = (line + " " + w).strip()
        if canv.stringWidth(test, font_name, font_size) <= max_w:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    out = []
    for l in "\n".join(lines).split("\n"):
        if l == "":
            out.append("")
            continue
        sub = ""
        for w in l.split():
            test = (sub + " " + w).strip()
            if canv.stringWidth(test, font_name, font_size) <= max_w:
                sub = test
            else:
                if sub:
                    out.append(sub)
                sub = w
        if sub:
            out.append(sub)
    return out or ["-"]

def draw_heading(canv, text, y, size=14):
    canv.setFont("Helvetica-Bold", size)
    canv.drawString(LM, y, text)
    return y

def draw_paragraph(canv, y, title, body, size=10, line_height=LINE_HEIGHT, space_after=BLOCK_SPACE):
    canv.setFont("Helvetica-Bold", size)
    canv.drawString(LM, y, title)
    y -= line_height
    canv.setFont("Helvetica", size)
    for line in wrap_lines(body, "Helvetica", size, CONTENT_W, canv):
        canv.drawString(LM, y, line)
        y -= line_height
        if y < BM:
            canv.showPage()
            y = PAGE_H - TM
            canv.setFont("Helvetica", size)
    return y - space_after

def draw_table(canv, y, data):
    # Solo se usa cuando reportlab está disponible
    table = Table(data, colWidths=[CONTENT_W/2, CONTENT_W/2])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F2F2F2")),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor("#BBBBBB")),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    w, h = table.wrapOn(canv, CONTENT_W, PAGE_H)
    if y - h < BM:
        canv.showPage()
        y = PAGE_H - TM
    table.drawOn(canv, LM, y - h)
    return y - h - TABLE_SPACE  # más espacio tras la tabla

def draw_eval(canv, y, label, score_text, size=10, line_height=LINE_HEIGHT, space_after=BLOCK_SPACE):
    canv.setFont("Helvetica-Bold", size)
    canv.drawString(LM, y, label)
    y -= line_height
    canv.setFont("Helvetica", size)
    canv.drawString(LM, y, f"Evaluación de Riesgo: {score_text if score_text else '-'}")
    return y - space_after

def section_block(canv, num, title, pregunta, narrativa, eval_text):
    y = canv._curr_y
    if y < BM + 260:
        canv.showPage(); y = PAGE_H - TM
    y = draw_heading(canv, f"{num}. {title}", y, size=12) - 12
    canv.setFont("Helvetica-Oblique", 9)
    for line in wrap_lines("Pregunta orientadora: " + (pregunta or "-"), "Helvetica-Oblique", 9, CONTENT_W, canv):
        canv.drawString(LM, y, line)
        y -= LINE_HEIGHT
        if y < BM:
            canv.showPage(); y = PAGE_H - TM; canv.setFont("Helvetica-Oblique", 9)
    y -= 8  # respiro tras la pregunta
    y = draw_paragraph(canv, y, "Narrativa o justificación:", narrativa or "-", line_height=LINE_HEIGHT, space_after=BLOCK_SPACE)
    y = draw_eval(canv, y, "Resultado:", eval_text, line_height=LINE_HEIGHT, space_after=BLOCK_SPACE + SECTION_EXTRA_GAP)
    canv._curr_y = y

def build_pdf(data, logo_bytes=None):
    if canvas is None:
        raise RuntimeError("ReportLab no está instalado. Instala: pip install reportlab")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c._curr_y = PAGE_H - TM

    # Encabezado
    if logo_bytes and ImageReader:
        try:
            img = ImageReader(io.BytesIO(logo_bytes))
            c.drawImage(img, LM, c._curr_y-20, width=90, height=30, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    c.setFont("Helvetica-Bold", 16)
    c.drawRightString(PAGE_W - RM, c._curr_y, "Formulario Comité de Riesgos")
    c._curr_y -= 22
    c.setFont("Helvetica", 9)
    c.drawRightString(PAGE_W - RM, c._curr_y, f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c._curr_y -= 20

    # 1. Resumen Ejecutivo
    c._curr_y = draw_heading(c, "1. Resumen Ejecutivo de la Operación", c._curr_y, size=13) - 14
    resumen_tbl = [
        ["Nombre del cliente:", data.get("nombre_cliente","")],
        ["Destino de los fondos:", data.get("destino_fondos","")],
        ["Monto solicitado:", data.get("monto_solicitado","")],
        ["Dirección de garantía:", data.get("direccion_garantia","")],
        ["Garantía ofrecida:", data.get("garantia","")],
        ["Fecha:", data.get("fecha","")],
        ["Score:", data.get("score","")],
        ["Calificación actual:", data.get("calificacion_actual","")],
        ["Peor calificación:", data.get("peor_calificacion","")],
        ["Responsable del análisis:", data.get("responsable","")],
        ["Expediente de riesgo (ID/enlace interno):", data.get("risk_file","")],
    ]
    c._curr_y = draw_table(c, c._curr_y, [["Campo","Valor"], *resumen_tbl])

    # 2. Instrucciones
    c._curr_y = draw_paragraph(c, c._curr_y, "2. Instrucciones Generales", INSTRUCCIONES,
                               line_height=LINE_HEIGHT, space_after=BLOCK_SPACE + 6)

    # 3–9
    section_block(c, 3, "Riesgos materiales identificados", P_Q3, data.get("s3_narrativa"), data.get("s3_eval"))
    section_block(c, 4, "Coherencia global de la operación", P_Q4, data.get("s4_narrativa"), data.get("s4_eval"))
    section_block(c, 5, "Justificación de excepciones al modelo", P_Q5, data.get("s5_narrativa"), data.get("s5_eval"))
    section_block(c, 6, "Fortalezas compensatorias claras", P_Q6, data.get("s6_narrativa"), data.get("s6_eval"))
    section_block(c, 7, "Reputación / trayectoria del cliente", P_Q7, data.get("s7_narrativa"), data.get("s7_eval"))
    section_block(c, 8, "Relación cliente–empresa / estrategia comercial", P_Q8, data.get("s8_narrativa"), data.get("s8_eval"))
    section_block(c, 9, "Condiciones de salida o repago alternativo", P_Q9, data.get("s9_narrativa"), data.get("s9_eval"))

    # 10. Recomendación
    y = c._curr_y
    if y < BM + 150:
        c.showPage(); y = PAGE_H - TM
    y = draw_heading(c, "10. Recomendación del Analista", y, size=12) - 12
    y = draw_paragraph(c, y, "Recomendaciones y comentarios:", data.get("recomendacion_analista",""),
                       line_height=LINE_HEIGHT, space_after=BLOCK_SPACE)
    c._curr_y = y

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

# ------------- UI Streamlit -------------
st.set_page_config(page_title="Comité de Riesgos", page_icon="🛡️", layout="centered")
st.title("Formulario de Evaluación para Comité de Riesgos")
st.caption("Complete todas las secciones y descargue el PDF.")

with st.sidebar:
    logo_file = st.file_uploader("Logo (PNG/JPG, opcional)", type=["png","jpg","jpeg"])
    nombre_pdf_base = st.text_input("Nombre base", value="Comite_Riesgos")

with st.form("form_riesgos"):
    # 1) Resumen Ejecutivo
    st.subheader("1) Resumen Ejecutivo de la Operación")
    c1, c2 = st.columns(2)
    with c1:
        nombre_cliente = st.text_input("Nombre del cliente *")
    with c2:
        destino_fondos = st.text_input("Destino de los fondos *")
    c3, c4 = st.columns(2)
    with c3:
        monto_solicitado = st.text_input("Monto solicitado *")
    with c4:
        direccion_garantia = st.text_input("Dirección de garantía *")
    c5, c6 = st.columns(2)
    with c5:
        garantia = st.text_input("Garantía ofrecida *")
    with c6:
        fecha = st.date_input("Fecha *", value=datetime.today()).strftime("%Y-%m-%d")
    c7, c8 = st.columns(2)
    with c7:
        score = st.text_input("Score *")
    with c8:
        calificacion_actual = st.text_input("Calificación actual *")
    c9, c10 = st.columns(2)
    with c9:
        peor_calificacion = st.text_input("Peor calificación *")
    with c10:
        responsable = st.text_input("Responsable del análisis *")
    risk_file = st.text_input("Expediente de riesgo (ID/enlace interno)")

    # 2) Instrucciones
    st.markdown("### 2) Instrucciones Generales")
    st.write(INSTRUCCIONES)
    st.markdown("---")

    # 3–9 con evaluaciones en texto
    st.subheader("3) Riesgos materiales identificados")
    st.caption(P_Q3)
    s3_narrativa = st.text_area("Narrativa (S3) *")
    s3_eval = st.selectbox("Evaluación (S3) *", OPCIONES_EVAL)

    st.subheader("4) Coherencia global de la operación")
    st.caption(P_Q4)
    s4_narrativa = st.text_area("Narrativa (S4) *")
    s4_eval = st.selectbox("Evaluación (S4) *", OPCIONES_EVAL)

    st.subheader("5) Justificación de excepciones al modelo")
    st.caption(P_Q5)
    s5_narrativa = st.text_area("Narrativa (S5) *")
    s5_eval = st.selectbox("Evaluación (S5) *", OPCIONES_EVAL)

    st.subheader("6) Fortalezas compensatorias claras")
    st.caption(P_Q6)
    s6_narrativa = st.text_area("Narrativa (S6) *")
    s6_eval = st.selectbox("Evaluación (S6) *", OPCIONES_EVAL)

    st.subheader("7) Reputación / trayectoria del cliente")
    st.caption(P_Q7)
    s7_narrativa = st.text_area("Narrativa (S7) *")
    s7_eval = st.selectbox("Evaluación (S7) *", OPCIONES_EVAL)

    st.subheader("8) Relación cliente–empresa / estrategia comercial")
    st.caption(P_Q8)
    s8_narrativa = st.text_area("Narrativa (S8) *")
    s8_eval = st.selectbox("Evaluación (S8) *", OPCIONES_EVAL)

    st.subheader("9) Condiciones de salida o repago alternativo")
    st.caption(P_Q9)
    s9_narrativa = st.text_area("Narrativa (S9) *")
    s9_eval = st.selectbox("Evaluación (S9) *", OPCIONES_EVAL)

    # 10) Recomendación
    st.subheader("10) Recomendación del Analista")
    recomendacion_analista = st.text_area("Recomendaciones y comentarios *")

    submitted = st.form_submit_button("Generar PDF")

if submitted:
    # Validaciones mínimas
    faltan = []
    campos = [
        ("Nombre del cliente", nombre_cliente),
        ("Destino de los fondos", destino_fondos),
        ("Monto solicitado", monto_solicitado),
        ("Dirección de garantía", direccion_garantia),
        ("Garantía ofrecida", garantia),
        ("Fecha", fecha),
        ("Score", score),
        ("Calificación actual", calificacion_actual),
        ("Peor calificación", peor_calificacion),
        ("Responsable del análisis", responsable),
        ("Narrativa S3", s3_narrativa), ("Narrativa S4", s4_narrativa),
        ("Narrativa S5", s5_narrativa), ("Narrativa S6", s6_narrativa),
        ("Narrativa S7", s7_narrativa), ("Narrativa S8", s8_narrativa),
        ("Narrativa S9", s9_narrativa), ("Recomendación", recomendacion_analista),
    ]
    for lbl, val in campos:
        if not str(val).strip():
            faltan.append(lbl)
    evals = [("S3", s3_eval), ("S4", s4_eval), ("S5", s5_eval),
             ("S6", s6_eval), ("S7", s7_eval), ("S8", s8_eval), ("S9", s9_eval)]
    faltan_eval = [f"Evaluación {k}" for k, v in evals if v not in OPCIONES_EVAL or v == ""]
    faltan += faltan_eval

    if faltan:
        st.error("Faltan campos: " + ", ".join(faltan))
    else:
        data = {
            "nombre_cliente": nombre_cliente,
            "destino_fondos": destino_fondos,
            "monto_solicitado": monto_solicitado,
            "direccion_garantia": direccion_garantia,
            "garantia": garantia,
            "fecha": fecha,
            "score": score,
            "calificacion_actual": calificacion_actual,
            "peor_calificacion": peor_calificacion,
            "responsable": responsable,
            "risk_file": risk_file,
            "s3_narrativa": s3_narrativa, "s3_eval": s3_eval,
            "s4_narrativa": s4_narrativa, "s4_eval": s4_eval,
            "s5_narrativa": s5_narrativa, "s5_eval": s5_eval,
            "s6_narrativa": s6_narrativa, "s6_eval": s6_eval,
            "s7_narrativa": s7_narrativa, "s7_eval": s7_eval,
            "s8_narrativa": s8_narrativa, "s8_eval": s8_eval,
            "s9_narrativa": s9_narrativa, "s9_eval": s9_eval,
            "recomendacion_analista": recomendacion_analista,
        }

        try:
            logo_bytes = logo_file.read() if logo_file else None
            pdf_bytes = build_pdf(data, logo_bytes=logo_bytes)
            nombre_archivo = f"{nombre_pdf_base}_{nombre_cliente}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            st.download_button("Descargar PDF", data=pdf_bytes, file_name=nombre_archivo, mime="application/pdf")
        except RuntimeError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Ocurrió un error al generar el PDF: {e}")
