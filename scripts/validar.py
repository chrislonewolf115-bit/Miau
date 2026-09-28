#!/usr/bin/env python3
"""Validaciones básicas de consistencia sobre un snapshot del Panel de Ahorro.

Uso:
    python3 scripts/validar.py                  # valida el snapshot más reciente de data/
    python3 scripts/validar.py data/snapshot-2026-09-28_1930.json

Termina con código 1 si hay ERRORES; las ADVERTENCIAS no cambian el código de salida.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

MES_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
FECHA_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
TARJETAS = {"Bci", "Cencosud", "Efectivo"}
# Categorías que el dashboard agrupa como "Supermercado" (vista Súper).
CATS_SUPER = {"Supermercado", "Supermercado (Lider)", "Verduleria/Frutas"}

errores = []
advertencias = []


def err(msg):
    errores.append(msg)


def warn(msg):
    advertencias.append(msg)


def es_entero(v):
    return isinstance(v, int) and not isinstance(v, bool)


def es_numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt(n):
    return "$" + f"{round(n):,}".replace(",", ".")


def snapshot_mas_reciente():
    candidatos = list(DATA.glob("*.json"))
    if not candidatos:
        sys.exit("No hay snapshots en data/.")

    def clave(p):
        with open(p, encoding="utf-8") as f:
            return (json.load(f).get("exportado_en") or "", p.name)

    return max(candidatos, key=clave)


def validar_ids_duplicados(snap):
    """doc_id duplicados. El export actual quita el _id, así que además se buscan
    documentos idénticos (típico al importar dos veces el mismo snapshot)."""
    for col in ["movimientos", "obligaciones", "cuotas_activas", "ingresos", "jumbo_categorias"]:
        docs = snap.get(col) or []
        ids = [d.get("doc_id", d.get("_id")) for d in docs if d.get("doc_id", d.get("_id")) is not None]
        for i, n in Counter(ids).items():
            if n > 1:
                err(f"{col}: doc_id '{i}' aparece {n} veces")
        firmas = Counter(
            json.dumps({k: v for k, v in d.items() if k not in ("doc_id", "_id")}, sort_keys=True, ensure_ascii=False)
            for d in docs
        )
        for firma, n in firmas.items():
            if n > 1:
                d = json.loads(firma)
                resumen = d.get("comercio") or d.get("nombre") or d.get("descripcion") or d.get("boleta") or firma[:60]
                warn(f"{col}: documento idéntico repetido {n} veces ({d.get('fecha', '')} {resumen} {d.get('monto', '')})".replace("  ", " "))


def validar_movimientos(movs):
    for i, m in enumerate(movs):
        ref = f"movimientos[{i}] {m.get('fecha')} {m.get('comercio')}"
        if not FECHA_RE.match(str(m.get("fecha", ""))):
            err(f"{ref}: fecha inválida '{m.get('fecha')}'")
        if not MES_RE.match(str(m.get("mes", ""))):
            err(f"{ref}: mes inválido '{m.get('mes')}'")
        elif str(m.get("fecha", ""))[:7] != m.get("mes"):
            err(f"{ref}: mes '{m.get('mes')}' no coincide con la fecha")
        if not es_numero(m.get("monto")) or m.get("monto") <= 0:
            err(f"{ref}: monto inválido '{m.get('monto')}'")
        if m.get("tarjeta") not in TARJETAS:
            warn(f"{ref}: tarjeta desconocida '{m.get('tarjeta')}'")
        for campo in ("recurrente", "reembolsado"):
            if campo in m and not isinstance(m[campo], bool):
                err(f"{ref}: '{campo}' debe ser true/false, es {m[campo]!r}")
        ca, ct = m.get("cuota_actual"), m.get("cuota_total")
        if ca is not None or ct is not None:
            if not (es_entero(ca) and es_entero(ct)):
                err(f"{ref}: cuota_actual/cuota_total deben ser ambos enteros o ambos null ({ca}/{ct})")
            elif not 1 <= ca <= ct:
                err(f"{ref}: cuota {ca}/{ct} fuera de rango")


def validar_reembolsados(movs):
    """Los movimientos reembolsado=true no deben sumar a la línea base de gasto variable.

    El dashboard los excluye del gasto variable mensual, pero la vista "Súper"
    suma todo lo de categoría supermercado con recurrente != false, sin mirar
    'reembolsado'. Aquí se recalcula la línea base correcta y se avisa de los
    casos que el dashboard contaría de más.
    """
    base = defaultdict(float)
    reemb = defaultdict(float)
    for m in movs:
        if not es_numero(m.get("monto")):
            continue
        if m.get("reembolsado") is True:
            reemb[m.get("mes")] += m["monto"]
            ref = f"{m.get('fecha')} {m.get('comercio')} {fmt(m['monto'])}"
            if m.get("recurrente") is True:
                warn(f"reembolsado y recurrente a la vez: {ref} — un gasto reembolsado no debería ser parte de la línea base")
            if m.get("categoria") in CATS_SUPER and m.get("recurrente") is not False:
                warn(f"reembolsado en supermercado sin recurrente=false: {ref} — la vista Súper del dashboard lo suma a la línea base; marcarlo recurrente=false")
        else:
            base[m.get("mes")] += m["monto"]
    return base, reemb


def validar_cuotas(nombre, docs, campo_monto, campo_desc):
    for i, c in enumerate(docs):
        ref = f"{nombre}[{i}] {c.get(campo_desc)}"
        ca, ct = c.get("cuota_actual_ref"), c.get("cuota_total")
        if not (es_entero(ca) and es_entero(ct)):
            err(f"{ref}: cuota_actual_ref/cuota_total deben ser enteros ({ca!r}/{ct!r})")
        elif ca > ct:
            err(f"{ref}: cuota_actual_ref ({ca}) > cuota_total ({ct})")
        elif ca < 1:
            err(f"{ref}: cuota_actual_ref ({ca}) < 1")
        if not MES_RE.match(str(c.get("mes_referencia", ""))):
            err(f"{ref}: mes_referencia inválido '{c.get('mes_referencia')}'")
        if not es_numero(c.get(campo_monto)) or c.get(campo_monto) <= 0:
            err(f"{ref}: {campo_monto} inválido '{c.get(campo_monto)}'")


def validar_ingresos(ingresos):
    for i, g in enumerate(ingresos):
        ref = f"ingresos[{i}] {g.get('nombre')}"
        if not es_numero(g.get("monto")):
            err(f"{ref}: monto inválido '{g.get('monto')}'")
        ini, fin = g.get("fecha_inicio"), g.get("fecha_termino")
        # El dashboard compara estos campos contra meses 'AAAA-MM'.
        if not MES_RE.match(str(ini or "")):
            err(f"{ref}: fecha_inicio debe ser 'AAAA-MM', es '{ini}'")
        if fin is not None and not MES_RE.match(str(fin)):
            err(f"{ref}: fecha_termino debe ser 'AAAA-MM' o null, es '{fin}'")
        if fin and ini and fin < ini:
            err(f"{ref}: fecha_termino ({fin}) anterior a fecha_inicio ({ini})")


def validar_jumbo(filas, movs):
    for i, r in enumerate(filas):
        ref = f"jumbo_categorias[{i}] boleta {r.get('boleta')}"
        if str(r.get("fecha", ""))[:7] != r.get("mes"):
            err(f"{ref}: mes '{r.get('mes')}' no coincide con fecha '{r.get('fecha')}'")
        if not es_numero(r.get("monto")):
            err(f"{ref}: monto inválido '{r.get('monto')}'")
    fechas_mov = {m.get("fecha") for m in movs if m.get("categoria") in CATS_SUPER}
    for boleta, fecha in sorted({(r.get("boleta"), r.get("fecha")) for r in filas}, key=str):
        if fecha not in fechas_mov:
            warn(f"jumbo_categorias: boleta {boleta} ({fecha}) no tiene un movimiento de supermercado ese día")


def validar_config(cfg):
    if not isinstance(cfg, dict):
        err("config: falta o no es un objeto")
        return
    for campo in ("linea_base_variable", "ahorro_inicial", "vacaciones_monto", "objetivo_discrecional"):
        if campo in cfg and not es_numero(cfg[campo]):
            err(f"config.{campo}: debe ser numérico, es {cfg[campo]!r}")
    rec = cfg.get("recortes")
    if not isinstance(rec, dict) or not all(k in rec for k in ("moderado", "conservador", "agresivo")):
        err("config.recortes: debe tener moderado, conservador y agresivo")
    if cfg.get("meta_pie_casa") is not None and not es_numero(cfg["meta_pie_casa"]):
        err(f"config.meta_pie_casa: debe ser numérico o null, es {cfg['meta_pie_casa']!r}")


def main():
    path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else snapshot_mas_reciente()
    with open(path, encoding="utf-8") as f:
        snap = json.load(f)
    print(f"Validando {path.name} (exportado_en={snap.get('exportado_en')})\n")

    for col in ["movimientos", "obligaciones", "cuotas_activas", "ingresos", "jumbo_categorias"]:
        if not isinstance(snap.get(col), list):
            err(f"{col}: falta o no es una lista")
            snap[col] = []

    movs = snap["movimientos"]
    validar_ids_duplicados(snap)
    validar_movimientos(movs)
    base, reemb = validar_reembolsados(movs)
    validar_cuotas("cuotas_activas", snap["cuotas_activas"], "monto_mensual", "descripcion")
    validar_cuotas("obligaciones", snap["obligaciones"], "monto_ref", "nombre")
    validar_ingresos(snap["ingresos"])
    validar_jumbo(snap["jumbo_categorias"], movs)
    validar_config(snap.get("config"))

    print("Gasto variable por mes (sin reembolsados):")
    for mes in sorted(set(base) | set(reemb), key=str):
        extra = f"   (+{fmt(reemb[mes])} reembolsado, excluido)" if reemb.get(mes) else ""
        print(f"  {mes}  {fmt(base.get(mes, 0)):>14}{extra}")
    print()

    for a in advertencias:
        print(f"ADVERTENCIA  {a}")
    for e in errores:
        print(f"ERROR        {e}")
    print(f"\n{len(errores)} errores, {len(advertencias)} advertencias.")
    sys.exit(1 if errores else 0)


if __name__ == "__main__":
    main()
