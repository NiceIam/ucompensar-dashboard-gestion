"""
Genera las imágenes (heatmap de tabla de verdad y 3 diagramas de flujo)
para el bloque de '¿Qué alternativa innovadora tengo?' del trabajo de
Lógica Matemática del primer semestre.

Salida: PNGs en /sessions/nice-vigilant-tesla/mnt/outputs/img_logica/
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D

OUT = "/sessions/nice-vigilant-tesla/mnt/outputs/img_logica"
os.makedirs(OUT, exist_ok=True)

# Colores institucionales (azul Ucompensar + neutros)
NAVY = "#1F4E78"
ORANGE = "#E07B00"
GREEN_OK = "#2E7D32"
RED_BAD = "#B71C1C"
YELLOW = "#F9A825"
GREY = "#9E9E9E"
LIGHT = "#E3F2FD"

plt.rcParams["font.family"] = "DejaVu Sans"

# ---------------------------------------------------------------------------
# 1) HEATMAP DE TABLA DE VERDAD
# ---------------------------------------------------------------------------
# Variables proposicionales:
#   p = el cliente tiene presupuesto suficiente
#   q = el cliente busca propiedad en la zona objetivo
#   r = el cliente puede pagar la cuota inicial
#   s = el cliente está disponible para visita esta semana
#
# Clasificación:
#   CALIENTE  =  p ∧ q ∧ r ∧ s
#   TIBIO     = (p ∧ q ∧ r) ∧ ¬s
#   FRÍO      =  resto
#
# (Estas son las reglas de la Alternativa 1 — booleanas estrictas.)


def truth_value(p, q, r, s):
    if p and q and r and s:
        return "CALIENTE", 2
    if p and q and r and not s:
        return "TIBIO", 1
    return "FRÍO", 0


rows = []
for p in [1, 0]:
    for q in [1, 0]:
        for r in [1, 0]:
            for s in [1, 0]:
                label, value = truth_value(p, q, r, s)
                rows.append([p, q, r, s, value, label])

# Ordenar por código binario descendente para que CALIENTE quede arriba
rows.sort(key=lambda x: -(x[0] * 8 + x[1] * 4 + x[2] * 2 + x[3]))

fig, ax = plt.subplots(figsize=(10, 8))
mat = np.zeros((16, 5))
for i, row in enumerate(rows):
    mat[i, :4] = row[:4]  # p, q, r, s
    mat[i, 4] = row[4]    # categoría 0/1/2

# Pintamos las primeras cuatro columnas en gris azulado y la quinta en colores
for i in range(16):
    for j in range(4):
        col = NAVY if mat[i, j] == 1 else "#FFFFFF"
        ax.add_patch(plt.Rectangle((j, 15 - i), 1, 1, facecolor=col, edgecolor="#999", linewidth=0.6))
        txt = "V" if mat[i, j] == 1 else "F"
        ax.text(j + 0.5, 15 - i + 0.5, txt, ha="center", va="center",
                color="white" if mat[i, j] == 1 else "#333", fontsize=11, fontweight="bold")
    cat_color = {0: RED_BAD, 1: YELLOW, 2: GREEN_OK}[mat[i, 4]]
    cat_label = rows[i][5]
    ax.add_patch(plt.Rectangle((4, 15 - i), 2, 1, facecolor=cat_color, edgecolor="#999", linewidth=0.6))
    ax.text(5, 15 - i + 0.5, cat_label, ha="center", va="center",
            color="white", fontsize=10, fontweight="bold")

# Encabezados
headers = ["p", "q", "r", "s", "Tipo"]
for j, h in enumerate(headers):
    w = 1 if j < 4 else 2
    ax.add_patch(plt.Rectangle((j if j < 4 else 4, 16), w, 0.9, facecolor=NAVY, edgecolor="#666"))
    ax.text((j + 0.5) if j < 4 else 5, 16.45, h, ha="center", va="center",
            color="white", fontsize=14, fontweight="bold")

ax.set_xlim(-0.2, 6.2)
ax.set_ylim(-0.2, 17.2)
ax.set_aspect("equal")
ax.axis("off")

# Leyenda
legend_elements = [
    plt.Rectangle((0, 0), 1, 1, facecolor=GREEN_OK, label="CALIENTE (alta prioridad)"),
    plt.Rectangle((0, 0), 1, 1, facecolor=YELLOW, label="TIBIO (seguimiento)"),
    plt.Rectangle((0, 0), 1, 1, facecolor=RED_BAD, label="FRÍO (descartar / nutrir)"),
]
ax.legend(handles=legend_elements, loc="upper center", bbox_to_anchor=(0.5, -0.02),
          ncol=3, frameon=False, fontsize=10)

plt.title("Tabla de verdad — Clasificación lógica del cliente inmobiliario",
          fontsize=13, fontweight="bold", pad=18, color=NAVY)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "01_tabla_verdad.png"), dpi=170, bbox_inches="tight")
plt.close(fig)


# ---------------------------------------------------------------------------
# Helpers para diagramas de flujo
# ---------------------------------------------------------------------------
def box(ax, x, y, w, h, text, color, text_color="white", fontsize=10):
    """Caja con esquinas redondeadas."""
    patch = FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                           boxstyle="round,pad=0.06",
                           linewidth=1.2, edgecolor="#333", facecolor=color)
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center",
            color=text_color, fontsize=fontsize, fontweight="bold", wrap=True)


def diamond(ax, x, y, w, h, text, color=YELLOW, text_color="#333", fontsize=9):
    """Rombo de decisión."""
    pts = [[x, y + h / 2], [x + w / 2, y], [x, y - h / 2], [x - w / 2, y]]
    ax.add_patch(plt.Polygon(pts, closed=True, linewidth=1.2,
                             edgecolor="#333", facecolor=color))
    ax.text(x, y, text, ha="center", va="center",
            color=text_color, fontsize=fontsize, fontweight="bold", wrap=True)


def arrow(ax, x1, y1, x2, y2, label="", offset=(0.05, 0)):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                                 arrowstyle="-|>", mutation_scale=15,
                                 linewidth=1.3, color="#333"))
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + offset[0], my + offset[1], label, fontsize=9,
                color="#333", ha="left", va="center",
                bbox=dict(facecolor="white", edgecolor="none", pad=1.5))


def setup(figsize=(7, 9)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")
    ax.set_aspect("equal")
    return fig, ax


# ---------------------------------------------------------------------------
# 2) DIAGRAMA DE FLUJO — ALTERNATIVA 1 (REGLAS BOOLEANAS)
# ---------------------------------------------------------------------------
fig, ax = setup()
box(ax, 5, 11.2, 4.5, 0.9, "INICIO\nCliente entra al chatbot", NAVY)
arrow(ax, 5, 10.7, 5, 10.2)

box(ax, 5, 9.7, 6, 0.9, "Capturar p, q, r, s\n(4 preguntas cerradas)", "#455A64")
arrow(ax, 5, 9.2, 5, 8.7)

diamond(ax, 5, 8.0, 5.5, 1.4, "¿p ∧ q ∧ r ∧ s?")
arrow(ax, 7.75, 8.0, 8.05, 8.0, "Sí", offset=(0, 0.18))
arrow(ax, 2.25, 8.0, 1.95, 8.0, "No", offset=(-0.4, 0.18))

box(ax, 9, 8.0, 1.8, 0.9, "CALIENTE", GREEN_OK)
arrow(ax, 1, 7.55, 1, 6.9)

diamond(ax, 1, 6.2, 2.6, 1.3, "¿p ∧ q ∧ r\n∧ ¬s?", fontsize=8)
arrow(ax, 2.3, 6.2, 4.0, 6.2, "Sí")
arrow(ax, 1, 5.55, 1, 4.9, "No")

box(ax, 4.9, 6.2, 1.8, 0.9, "TIBIO", YELLOW, text_color="#333")
box(ax, 1, 4.45, 1.8, 0.9, "FRÍO", RED_BAD)

# Convergencia
arrow(ax, 9, 7.55, 9, 3.3)
arrow(ax, 4.9, 5.75, 4.9, 3.3)
arrow(ax, 1, 4.0, 1, 3.3)
box(ax, 5, 2.85, 6, 0.9, "Asignar a asesor según prioridad", "#455A64")
arrow(ax, 5, 2.4, 5, 1.9)
box(ax, 5, 1.5, 4.5, 0.9, "FIN", NAVY)

plt.title("Alternativa 1 — Diagrama de flujo del chatbot con reglas booleanas",
          fontsize=12, fontweight="bold", pad=15, color=NAVY)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "02_flujo_alt1.png"), dpi=170, bbox_inches="tight")
plt.close(fig)


# ---------------------------------------------------------------------------
# 3) DIAGRAMA DE FLUJO — ALTERNATIVA 2 (SCORING PONDERADO)
# ---------------------------------------------------------------------------
fig, ax = setup(figsize=(7.5, 10))
box(ax, 5, 11.4, 4.5, 0.9, "INICIO\nCliente entra al chatbot", NAVY)
arrow(ax, 5, 10.95, 5, 10.5)

box(ax, 5, 10.0, 6.5, 0.9, "Capturar p, q, r, s\nmás datos opcionales", "#455A64")
arrow(ax, 5, 9.55, 5, 9.1)

box(ax, 5, 8.6, 7.0, 0.9, "Asignar pesos:\np=3 · q=3 · r=2 · s=1", ORANGE)
arrow(ax, 5, 8.15, 5, 7.7)

box(ax, 5, 7.2, 5.2, 0.9, "score = Σ (peso · valor)", "#455A64")
arrow(ax, 5, 6.75, 5, 6.3)

diamond(ax, 5, 5.6, 5.2, 1.4, "¿score ≥ 7?")
arrow(ax, 7.6, 5.6, 9, 5.6, "Sí")
arrow(ax, 2.4, 5.6, 1, 5.6, "No")

box(ax, 9, 5.6, 1.8, 0.9, "CALIENTE", GREEN_OK)
arrow(ax, 1, 5.15, 1, 4.5)
diamond(ax, 1, 3.8, 2.6, 1.3, "¿score ≥ 4?", fontsize=9)
arrow(ax, 2.3, 3.8, 4.0, 3.8, "Sí")
arrow(ax, 1, 3.15, 1, 2.5, "No")
box(ax, 4.9, 3.8, 1.8, 0.9, "TIBIO", YELLOW, text_color="#333")
box(ax, 1, 2.05, 1.8, 0.9, "FRÍO", RED_BAD)

arrow(ax, 9, 5.15, 9, 1.4)
arrow(ax, 4.9, 3.35, 4.9, 1.4)
arrow(ax, 1, 1.6, 1, 1.4)
box(ax, 5, 1.0, 6.5, 0.9, "Enrutar y registrar score", NAVY)

plt.title("Alternativa 2 — Diagrama de flujo del chatbot con scoring ponderado",
          fontsize=12, fontweight="bold", pad=15, color=NAVY)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "03_flujo_alt2.png"), dpi=170, bbox_inches="tight")
plt.close(fig)


# ---------------------------------------------------------------------------
# 4) DIAGRAMA DE FLUJO — ALTERNATIVA 3 (HÍBRIDO REGLAS + IA)
# ---------------------------------------------------------------------------
fig, ax = setup(figsize=(8, 11))
box(ax, 5, 12.2, 4.8, 0.9, "INICIO\nCliente entra al chatbot", NAVY)
arrow(ax, 5, 11.75, 5, 11.3)

box(ax, 5, 10.8, 6.5, 0.9, "Saludo + 4 preguntas (p, q, r, s)", "#455A64")
arrow(ax, 5, 10.35, 5, 9.9)

diamond(ax, 5, 9.2, 5.5, 1.4, "¿Reglas dan respuesta\nclara (CALIENTE/FRÍO)?", fontsize=8)
arrow(ax, 7.75, 9.2, 9, 9.2, "Sí")
arrow(ax, 2.25, 9.2, 1, 9.2, "No (TIBIO o ambiguo)")

box(ax, 9, 9.2, 1.8, 0.9, "Clasificar\ndirecto", GREEN_OK, fontsize=9)
arrow(ax, 1, 8.75, 1, 7.9)

box(ax, 1, 7.45, 2.2, 0.9, "Activar agente\nLLM (Gemini)", ORANGE, fontsize=9)
arrow(ax, 1, 7.0, 1, 6.5)

box(ax, 1, 6.05, 2.6, 0.9, "Pregunta abierta\nal cliente", "#455A64", fontsize=9)
arrow(ax, 1, 5.6, 1, 5.1)

box(ax, 1, 4.65, 2.6, 0.9, "LLM interpreta\ny re-evalúa", ORANGE, fontsize=9)
arrow(ax, 1, 4.2, 1, 3.7)

diamond(ax, 1, 3.0, 2.6, 1.3, "¿Cliente\ncalificado?", fontsize=9)
arrow(ax, 2.3, 3.0, 4.0, 3.0, "Sí")
arrow(ax, 1, 2.35, 1, 1.7, "No")

box(ax, 4.9, 3.0, 1.8, 0.9, "CALIENTE/TIBIO", GREEN_OK, fontsize=9)
box(ax, 1, 1.25, 1.8, 0.9, "FRÍO", RED_BAD)

arrow(ax, 9, 8.75, 9, 0.7)
arrow(ax, 4.9, 2.55, 4.9, 0.7)
arrow(ax, 1, 0.8, 1, 0.7)
box(ax, 5, 0.3, 6.5, 0.9, "Asignar a asesor + log conversación", NAVY)

plt.title("Alternativa 3 — Diagrama de flujo del chatbot híbrido (reglas + IA)",
          fontsize=12, fontweight="bold", pad=15, color=NAVY)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "04_flujo_alt3.png"), dpi=170, bbox_inches="tight")
plt.close(fig)

print("OK — imágenes generadas en", OUT)
for f in sorted(os.listdir(OUT)):
    print(" -", f, os.path.getsize(os.path.join(OUT, f)), "bytes")
