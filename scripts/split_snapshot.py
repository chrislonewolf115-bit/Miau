#!/usr/bin/env python3
"""Separa un snapshot del Panel de Ahorro en un archivo JSON por colección.

Uso:
    python3 scripts/split_snapshot.py                     # usa el snapshot más reciente de data/
    python3 scripts/split_snapshot.py ~/Downloads/panel-ahorro-backup.json

Si el archivo indicado no está dentro de data/, se copia ahí como
data/snapshot-AAAA-MM-DD_HHMM.json (fecha tomada de "exportado_en").

Salida: data/split/<coleccion>.json, con los documentos ordenados de forma
estable para que los diffs de git muestren solo lo que cambió.
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SPLIT = DATA / "split"

COLECCIONES = ["movimientos", "obligaciones", "cuotas_activas", "ingresos", "jumbo_categorias"]

# Claves de orden por colección (el export no trae ids, así que ordenamos por contenido).
ORDEN = {
    "movimientos": ("fecha", "tarjeta", "comercio", "monto"),
    "obligaciones": ("nombre",),
    "cuotas_activas": ("tarjeta", "descripcion", "mes_referencia"),
    "ingresos": ("fecha_inicio", "nombre"),
    "jumbo_categorias": ("fecha", "boleta", "categoria", "monto"),
}


def cargar(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def escribir(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def clave_orden(doc, campos):
    # Tupla (es_none, valor-como-texto) para que None y tipos mezclados no rompan el sort.
    k = tuple((doc.get(c) is None, str(doc.get(c, ""))) for c in campos)
    return k + (json.dumps(doc, sort_keys=True, ensure_ascii=False),)


def snapshot_mas_reciente():
    candidatos = sorted(p for p in DATA.glob("*.json"))
    if not candidatos:
        sys.exit("No hay snapshots en data/. Pasa la ruta del archivo exportado como argumento.")
    return max(candidatos, key=lambda p: (cargar(p).get("exportado_en") or "", p.name))


def traer_a_data(path, snap):
    """Copia el export a data/ con nombre fechado si viene de otra carpeta."""
    if path.resolve().parent == DATA.resolve():
        return path
    exportado = snap.get("exportado_en")
    try:
        ts = datetime.fromisoformat(exportado.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        ts = datetime.now()
    destino = DATA / f"snapshot-{ts:%Y-%m-%d_%H%M}.json"
    if destino.exists():
        print(f"Ya existe {destino.relative_to(ROOT)}, no se sobrescribe.")
    else:
        shutil.copy2(path, destino)
        print(f"Copiado a {destino.relative_to(ROOT)}")
    return destino


def main():
    if len(sys.argv) > 1:
        origen = Path(sys.argv[1]).expanduser()
        snap = cargar(origen)
        origen = traer_a_data(origen, snap)
    else:
        origen = snapshot_mas_reciente()
        snap = cargar(origen)

    faltantes = [c for c in COLECCIONES + ["config"] if c not in snap]
    if faltantes:
        sys.exit(f"{origen.name}: no parece un export del Panel de Ahorro (faltan: {', '.join(faltantes)})")

    SPLIT.mkdir(parents=True, exist_ok=True)
    for col in COLECCIONES:
        docs = sorted(snap[col] or [], key=lambda d: clave_orden(d, ORDEN[col]))
        escribir(SPLIT / f"{col}.json", docs)
        print(f"  {col + '.json':24} {len(docs):5} documentos")
    escribir(SPLIT / "config.json", snap["config"])
    print(f"  {'config.json':24}     1 documento")
    escribir(SPLIT / "_meta.json", {"exportado_en": snap.get("exportado_en"), "origen": origen.name})
    print(f"Snapshot {origen.name} (exportado_en={snap.get('exportado_en')}) separado en data/split/")


if __name__ == "__main__":
    main()
