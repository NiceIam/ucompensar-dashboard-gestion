"""
Versión 2 — imágenes para el bloque "¿Qué alternativa novedosa de solución tengo?"
con la estructura nueva pedida por la usuaria:

  Propuesta 1: Tabla de verdad de 8 filas para V = p ∧ (q ∨ r)
  Propuesta 2: Diagrama de Venn con tres conjuntos A, B, C
  Propuesta 3: Diagrama de flujo SENCILLO del pseudocódigo

Salida: PNGs en /sessions/nice-vigilant-tesla/mnt/outputs/img_logica_v2/
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

OUT = "/sessions/nice-vigilant-tesla/mnt/outputs/img_logica_v2"
os.makedirs(OUT, exist_ok=True)

NAVY = "#1F4E78"
ORANGE = "#E07B00"
GREEN_OK = "#2E7D32"
RED_BAD = "#B71C1C"
YELLOW = "#F9A825"
LIGHT_BLUE = "#BBDEFB"
LIGHT_GREEN = "#C8E6C9"
LIGHT_PINK = "#F8BBD0"

plt.rcParams["font.family"] = "DejaVu Sans"

# =========================================================================
# 1) TABLA DE VERDAD — V = p ∧ (q ∨ r)
# =========================================================================
# Filas: p, q, r, (q ∨ r), V = p ∧ (q ∨ r)
rows = [
    [1, 1, 1],
    [1, 1, 0],
    [1, 0, 1],
    [1, 0, 0],
    [0, 1, 1],
    [0, 1, 0],
    [0, 0, 1],
    [0, 0, 0],
]
data = []
for p, q, r in rows:
    qor = q | r
    v = p & qor
    data.append([p, q, r, qor, v])

fig, ax = plt.subplots(figsize=(11, 7))

headers = ["p\n(presupuesto\n≥ 150 M)",
           "q\n(crédito\npre-aprobado)",
           "r\n(dinero de\ncontado)",
           "q ∨ r\n(tiene crédito\nO contado)",
           "V = p ∧ (q ∨ r)\n(cliente VIABLE)"]

col_widths = [1.6, 1.6, 1.6, 1.8, 2.0]
col_x = [0]
for w in col_widths:
    col_x.append(col_x[-1] + w)
total_w = col_x[-1]

# Encabezado
header_h = 1.4
for i, h in enumerate(headers):
    ax.add_patch(plt.Rectangle((col_x[i], 8), col_widths[i], header_h,
                               facecolor=NAVY, edgecolor="#333"))
    ax.text(col_x[i] + col_widths[i] / 2, 8 + header_h / 2, h,
            ha="center", va="center", color="white", fontsize=10, fontweight="bold")

# Filas
row_h = 0.85
for ri, row in enumerate(data):
    y = 8 - (ri + 1) * row_h
    for ci, val in enumerate(row):
        if ci < 4:
            face = LIGHT_BLUE if val == 1 else "white"
            text = "V" if val == 1 else "F"
            color_text = NAVY
        else:
            face = LIGHT_GREEN if val == 1 else LIGHT_PINK
            text = "V (Viable)" if val == 1 else "F (No viable)"
            color_text = GREEN_OK if val == 1 else RED_BAD
        ax.add_patch(plt.Rectangle((col_x[ci], y), col_widths[ci], row_h,
                                   facecolor=face, edgecolor="#999", linewidth=0.7))
        ax.text(col_x[ci] + col_widths[ci] / 2, y + row_h / 2, text,
                ha="center", va="center", color=color_text,
                fontsize=11 if ci < 4 else 10, fontweight="bold")

ax.set_xlim(-0.2, total_w + 0.2)
ax.set_ylim(-0.6, 9.7)
ax.set_aspect("equal")
ax.axis("off")
plt.title("Tabla de verdad — V = p ∧ (q ∨ r)\nClasificación de cliente VIABLE para el chatbot inmobiliario",
          fontsize=12, fontweight="bold", pad=14, color=NAVY)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "01_tabla_verdad.png"), dpi=170, bbox_inches="tight")
plt.close(fig)


# =========================================================================
# 2) DIAGRAMA DE VENN — A ∩ B ∩ C
# =========================================================================
fig, ax = plt.subplots(figsize=(9, 8))

# Tres círculos
c1 = Circle((-1.0, 0.7), 2.4, facecolor="#42A5F5", alpha=0.45, edgecolor="#1565C0", linewidth=2)
c2 = Circle(( 1.0, 0.7), 2.4, facecolor="#FFA726", alpha=0.45, edgecolor="#E65100", linewidth=2)
c3 = Circle(( 0.0,-1.0), 2.4, facecolor="#66BB6A", alpha=0.45, edgecolor="#2E7D32", linewidth=2)

ax.add_patch(c1)
ax.add_patch(c2)
ax.add_patch(c3)

# Etiquetas de los conjuntos (afuera, claras)
ax.text(-3.4, 2.5, "A", fontsize=26, fontweight="bold", color="#1565C0")
ax.text(-3.4, 1.9, "Inmuebles\nen Bogotá",
        fontsize=10, color="#1565C0", style="italic")

ax.text(3.0, 2.5, "B", fontsize=26, fontweight="bold", color="#E65100")
ax.text(3.0, 1.9, "Inmuebles tipo\nApartamento",
        fontsize=10, color="#E65100", style="italic")

ax.text(2.4, -3.0, "C", fontsize=26, fontweight="bold", color="#2E7D32")
ax.text(1.5, -3.6, "Inmuebles\n< 250 M COP",
        fontsize=10, color="#2E7D32", style="italic")

# Marcar la intersección triple
ax.plot([0], [0.05], marker="*", markersize=24, color="red", zorder=5)
ax.annotate("A ∩ B ∩ C\nLA SOLUCIÓN\n(apartamento, en Bogotá,\nmenos de 250 M)",
            xy=(0, 0.05), xytext=(4.3, -1.5),
            fontsize=10, fontweight="bold", color="red",
            arrowprops=dict(arrowstyle="->", color="red", lw=1.5),
            ha="left")

# Etiqueta del universo U
ax.add_patch(plt.Rectangle((-4.5, -4.3), 9, 8.0, fill=False, edgecolor="#666", linewidth=1.2, linestyle="--"))
ax.text(-4.3, 3.4, "U  =  todos los inmuebles disponibles",
        fontsize=11, fontweight="bold", color="#333")

ax.set_xlim(-5, 5)
ax.set_ylim(-4.8, 4.2)
ax.set_aspect("equal")
ax.axis("off")
plt.title("Diagrama de Venn — Búsqueda con A ∩ B ∩ C\n(intersección de los tres filtros del cliente)",
          fontsize=12, fontweight="bold", pad=10, color=NAVY)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "02_venn.png"), dpi=170, bbox_inches="tight")
plt.close(fig)


# =========================================================================
# 3) DIAGRAMA DE FLUJO SENCILLO — Pseudocódigo del chatbot
# =========================================================================
def box(ax, x, y, w, h, text, color, text_color="white", fontsize=11):
    patch = FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                           boxstyle="round,pad=0.06",
                           linewidth=1.2, edgecolor="#333", facecolor=color)
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center",
            color=text_color, fontsize=fontsize, fontweight="bold", wrap=True)


def diamond(ax, x, y, w, h, text, color=YELLOW, text_color="#333", fontsize=10):
    pts = [[x, y + h / 2], [x + w / 2, y], [x, y - h / 2], [x - w / 2, y]]
    ax.add_patch(plt.Polygon(pts, closed=True, linewidth=1.2,
                             edgecolor="#333", facecolor=color))
    ax.text(x, y, text, ha="center", va="center",
            color=text_color, fontsize=fontsize, fontweight="bold")


def arrow(ax, x1, y1, x2, y2, label="", offset=(0.12, 0.15)):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                                 arrowstyle="-|>", mutation_scale=16,
                                 linewidth=1.4, color="#333"))
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + offset[0], my + offset[1], label, fontsize=10,
                color="#333", fontweight="bold",
                bbox=dict(facecolor="white", edgecolor="none", pad=2))


fig, ax = plt.subplots(figsize=(8.5, 11))
ax.set_xlim(0, 10)
ax.set_ylim(0, 13)
ax.axis("off")
ax.set_aspect("equal")

box(ax, 5, 12.3, 4.5, 0.8, "INICIO", NAVY)
arrow(ax, 5, 11.9, 5, 11.5)

box(ax, 5, 11.0, 7, 0.9, "Saludo: «Bienvenido a InmobiliaryAI»", "#455A64")
arrow(ax, 5, 10.55, 5, 10.1)

box(ax, 5, 9.6, 7, 0.9, "Pregunta 1: ¿Cuál es su presupuesto?", "#455A64")
arrow(ax, 5, 9.15, 5, 8.7)

diamond(ax, 5, 8.0, 5.5, 1.4, "¿presupuesto ≥ 150 M?")
arrow(ax, 7.75, 8.0, 9, 8.0, "Sí", offset=(-0.2, 0.18))
arrow(ax, 2.25, 8.0, 1, 8.0, "No", offset=(-0.5, 0.18))

box(ax, 9, 7.3, 1.8, 0.9, "Sigue\npreguntando", GREEN_OK, fontsize=9)
box(ax, 1, 8.0, 2.0, 0.9, "«No tenemos\ninventario»", RED_BAD, fontsize=9)
arrow(ax, 1, 7.55, 1, 0.7)

arrow(ax, 9, 6.85, 5, 6.0)
box(ax, 5, 5.6, 7.5, 0.9, "Pregunta 2 y 3: crédito (q) y contado (r)", "#455A64")
arrow(ax, 5, 5.15, 5, 4.7)

diamond(ax, 5, 4.0, 5.5, 1.4, "¿q ∨ r? (¿alguna pago?)")
arrow(ax, 7.75, 4.0, 9, 4.0, "Sí", offset=(-0.2, 0.18))
arrow(ax, 2.25, 4.0, 1, 4.0, "No", offset=(-0.5, 0.18))

box(ax, 9, 3.2, 1.8, 0.9, "CLIENTE\nVIABLE", GREEN_OK, fontsize=10)
box(ax, 1, 3.2, 2.0, 0.9, "Enviar\nopciones por\ncorreo", YELLOW, text_color="#333", fontsize=9)

arrow(ax, 9, 2.75, 9, 1.7)
box(ax, 9, 1.3, 2.0, 0.9, "Llamar\nasesor VIP", NAVY, fontsize=10)
arrow(ax, 9, 0.85, 9, 0.5)

arrow(ax, 1, 2.75, 1, 1.7)
box(ax, 1, 1.3, 2.0, 0.9, "Guardar en\nlista de espera", "#455A64", fontsize=9)
arrow(ax, 1, 0.85, 1, 0.7)

box(ax, 5, 0.3, 4.5, 0.8, "FIN", NAVY)
arrow(ax, 9, 0.5, 7.25, 0.3)
arrow(ax, 1, 0.7, 2.75, 0.3)

plt.title("Diagrama de flujo del chatbot — Propuesta 3\n(estructura de control SI–ENTONCES paso a paso)",
          fontsize=12, fontweight="bold", pad=14, color=NAVY)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "03_diagrama_flujo.png"), dpi=170, bbox_inches="tight")
plt.close(fig)


# =========================================================================
# 4) Analogía visual — Portero de la discoteca (Propuesta 1)
# =========================================================================
fig, ax = plt.subplots(figsize=(10, 5))
ax.set_xlim(0, 10)
ax.set_ylim(0, 5)
ax.axis("off")
ax.set_aspect("equal")

# Persona en la fila
ax.plot([1.0], [2.5], marker="o", markersize=28, color="#FFC107")  # cabeza
ax.plot([1.0, 1.0], [2.2, 1.0], color="#0277BD", lw=4)             # cuerpo
ax.text(1.0, 0.3, "Cliente", ha="center", fontsize=10, fontweight="bold")

# Portero
ax.add_patch(FancyBboxPatch((3.4, 1.5), 1.4, 2.0, boxstyle="round,pad=0.1",
                             facecolor="#37474F", edgecolor="#000"))
ax.text(4.1, 2.5, "Portero\n(chatbot)", ha="center", va="center",
        fontsize=10, fontweight="bold", color="white")

# Lista de chequeo
ax.add_patch(FancyBboxPatch((5.6, 1.0), 2.5, 3.0, boxstyle="round,pad=0.1",
                             facecolor="white", edgecolor="#333"))
ax.text(6.85, 3.7, "Lista de chequeo", ha="center", fontsize=10, fontweight="bold")
ax.text(5.8, 3.1, "✓ p — presupuesto", fontsize=9, color="#1B5E20")
ax.text(5.8, 2.7, "✓ q — crédito", fontsize=9, color="#1B5E20")
ax.text(5.8, 2.3, "✓ r — contado", fontsize=9, color="#1B5E20")
ax.text(5.8, 1.7, "Regla:", fontsize=9, fontweight="bold")
ax.text(5.8, 1.3, "V = p ∧ (q ∨ r)", fontsize=10, fontweight="bold", color=NAVY)

# Flecha hacia adentro
ax.add_patch(FancyArrowPatch((1.7, 2.5), (3.3, 2.5), arrowstyle="-|>",
                              mutation_scale=18, color="#333", lw=1.5))

# Puerta y resultado
ax.add_patch(FancyBboxPatch((8.4, 1.0), 1.4, 3.0, boxstyle="round,pad=0.05",
                             facecolor=GREEN_OK, edgecolor="#1B5E20"))
ax.text(9.1, 2.7, "Cliente\nVIABLE", ha="center", va="center",
        fontsize=11, fontweight="bold", color="white")
ax.text(9.1, 1.5, "✓ pasa", ha="center", fontsize=10, color="white", fontweight="bold")

ax.add_patch(FancyArrowPatch((4.8, 2.5), (5.55, 2.5), arrowstyle="-|>",
                              mutation_scale=15, color="#333", lw=1.2))
ax.add_patch(FancyArrowPatch((8.1, 2.5), (8.35, 2.5), arrowstyle="-|>",
                              mutation_scale=18, color="#333", lw=1.5))

plt.title("Analogía — El chatbot funciona como un portero con su lista",
          fontsize=12, fontweight="bold", color=NAVY)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "04_analogia_portero.png"), dpi=170, bbox_inches="tight")
plt.close(fig)


print("OK — imágenes v2 generadas en", OUT)
for f in sorted(os.listdir(OUT)):
    print(" -", f, os.path.getsize(os.path.join(OUT, f)), "bytes")
