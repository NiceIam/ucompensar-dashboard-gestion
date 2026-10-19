"""Oraculo en pandas de los hallazgos de negocio (business_insights_service) — PI0320251.

Reimplementa las DEFINICIONES (no el codigo) sobre filas crudas en memoria, con Fraction para no arrastrar
errores de coma flotante. No importa nada del servicio: si el servicio tiene un error de formula, el oraculo no
lo copia. Se usa en pruebas diferenciales (datos aleatorios y sucios) y para validar los datos de ejemplo.

Entrada: filas (dicts) con las columnas canonicas
  productos: nombre, costo, stock
  ventas:    fecha, producto, cantidad, precio_unitario (opcional), total (opcional), cliente (opcional)
Salida: dict con las cifras que el servicio publica en `metrics`.
"""

import re
import unicodedata
from datetime import date, timedelta
from fractions import Fraction

import pandas as pd

_NUM = re.compile(r"\s*[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d{1,3})?\s*")
GENERIC = {"mostrador", "contado", "consumidor final", "cliente general", "varios", "sin cliente", "n/a"}
DAYS_PER_MONTH = 30


def key_of(text) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().split())


def num(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Fraction(str(value))
    if isinstance(value, str) and len(value) <= 200 and _NUM.fullmatch(value):
        return Fraction(value.strip())
    return None


def parse_date(value):
    if not isinstance(value, str):
        return None
    t = value.strip()
    if m := re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t):
        y, mo, d = map(int, m.groups())
    elif m := re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", t):
        d, mo, y = map(int, m.groups())
    else:
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def round_half_up(x: Fraction) -> int:
    """Redondeo comercial: .5 se aleja de cero (simetrico en negativos)."""
    magnitude = int((abs(x) * 2 + 1) // 2)
    return magnitude if x >= 0 else -magnitude


def compute(prods: list[dict], sales: list[dict], *, has_unit=True, has_total=True, has_client=True,
            max_date: date = date(2026, 10, 20) + timedelta(days=366)) -> dict:
    # --- productos: una fila por (producto normalizado) con existencias y costo unitario ponderado
    p = pd.DataFrame(
        [{"key": key_of(r["nombre"]), "name": r["nombre"], "cost": num(r.get("costo")), "stock": num(r.get("stock"))}
         for r in prods if r.get("nombre") is not None and key_of(r["nombre"]) != ""]
    )
    prod = {}
    for key, g in p.groupby("key", sort=False):
        value = Fraction(0)
        weight = Fraction(0)
        cost_sum = Fraction(0)
        n_cost = 0
        stock_total = Fraction(0)
        has_stock = False
        for _, r in g.iterrows():
            st = r["stock"]
            eff = Fraction(0) if st is None or st < 0 else st
            has_stock |= st is not None
            stock_total += eff
            c = r["cost"]
            if c is not None and c > 0:
                value += eff * c
                weight += eff
                cost_sum += c
                n_cost += 1
        if n_cost == 0:
            unit = None
        else:
            unit = value / weight if weight > 0 else cost_sum / n_cost
        prod[key] = {"name": g.iloc[0]["name"], "stock": stock_total, "value": value, "cost": unit,
                     "has_stock": has_stock}
    merchandise = sum((v["value"] for v in prod.values()), Fraction(0))

    # --- ventas validas: cantidad > 0, precio real legible y fecha legible entre 2000 y hoy + 366 dias
    dates = [parse_date(r.get("fecha")) for r in sales]
    lines = []
    for r, d in zip(sales, dates):
        if d is None or d < date(2000, 1, 1) or d > max_date:
            continue
        q = num(r.get("cantidad"))
        if q is None or q <= 0:
            continue
        unit = num(r.get("precio_unitario")) if has_unit else None
        total = num(r.get("total")) if has_total else None
        if unit is not None and unit >= 0:
            price, line = unit, q * unit
        elif total is not None and total >= 0:
            price, line = total / q, total
        else:
            continue
        client = key_of(r["cliente"]) if has_client and r.get("cliente") not in (None, "") else ""
        lines.append({"key": key_of(r["producto"]) if r.get("producto") is not None else "", "date": d, "qty": q,
                      "price": price, "line": line, "client": client,
                      "label": r.get("cliente")})
    if not lines:
        return {"period": None, "merchandise": merchandise}
    d0, d1 = min(l["date"] for l in lines), max(l["date"] for l in lines)
    days = (d1 - d0).days + 1
    s = pd.DataFrame(lines)
    revenue = sum((x for x in s["line"]), Fraction(0)) if len(s) else Fraction(0)

    matched = s[s["key"].isin(prod)] if len(s) else s
    cogs = Fraction(0)
    per = {}
    for key, g in matched.groupby("key", sort=False):
        pr = prod[key]
        units = sum(g["qty"], Fraction(0))
        rev = sum(g["line"], Fraction(0))
        entry = {"units": units, "rev": rev}
        if pr["cost"] is not None:
            cogs += units * pr["cost"]
            entry["profit"] = rev - units * pr["cost"]
            entry["margin"] = entry["profit"] / rev if rev > 0 else None
            below = g[g["price"] < pr["cost"]]
            entry["below"] = len(below) > 0
            entry["loss"] = sum((r.qty * pr["cost"] - r.line for r in below.itertuples()), Fraction(0))
        per[key] = entry

    out = {"period": (d0, d1, days), "merchandise": merchandise, "revenue": revenue, "cogs": cogs}
    out["months_inv"] = (merchandise * days / (cogs * DAYS_PER_MONTH)) if cogs > 0 else None

    profits = {k: v["profit"] for k, v in per.items() if "profit" in v}
    total_profit = sum(profits.values(), Fraction(0))
    stars = sorted(((k, v) for k, v in profits.items() if v > 0), key=lambda kv: (-kv[1], kv[0]))[:3]
    out["profit_total"] = total_profit
    out["stars"] = [(prod[k]["name"], v) for k, v in stars]

    restock = []
    for k, v in per.items():
        pr = prod[k]
        if pr["has_stock"] and v["units"] > 0:
            left = pr["stock"] / (v["units"] / days)
            if left < 15:
                restock.append((left, k))
    restock.sort()
    out["restock"] = [(prod[k]["name"], left) for left, k in restock]

    by_client = {}
    total_clients = sum((x for x in s["line"]), Fraction(0)) if len(s) else Fraction(0)
    for r in lines:
        if r["client"] and r["client"] not in GENERIC:
            by_client[r["client"]] = by_client.get(r["client"], Fraction(0)) + r["line"]
    ranked = sorted(by_client.values(), reverse=True)
    out["clients_n"] = len(ranked)
    out["client_top3"] = sum(ranked[:3], Fraction(0)) / total_clients if ranked and total_clients > 0 else None
    out["client_first"] = ranked[0] / total_clients if ranked and total_clients > 0 else None

    window_from = d1 - timedelta(days=min(90, days) - 1)
    # "se movio" = alguna venta VALIDA (cantidad > 0 y precio legible) con fecha en la ventana
    moved = {r["key"] for r in lines if window_from <= r["date"] <= d1}
    parked = [(k, v) for k, v in prod.items() if v["has_stock"] and v["stock"] > 0 and k not in moved]
    out["parked_money"] = sum((v["value"] for _k, v in parked), Fraction(0))
    out["parked_n"] = len(parked)

    flagged = []
    for k, v in per.items():
        if "profit" not in v or v["units"] <= 0:
            continue
        if v["below"] or (v["margin"] is not None and v["margin"] < Fraction(1, 10)):
            flagged.append((prod[k]["name"], v["below"], v["loss"]))
    out["margin_flagged_n"] = len(flagged)
    out["margin_losing_n"] = sum(1 for f in flagged if f[1])
    out["margin_loss"] = sum((f[2] for f in flagged if f[1]), Fraction(0))
    return out
