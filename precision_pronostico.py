"""
Precisión del pronóstico de lluvia (WRF del INAMHI) en las inundaciones de la SNGR.

Toma las inundaciones ya cruzadas con lluvia y caudal (eventos/inundaciones.csv, que
arma cruzar_eventos.py) y escribe una tabla por evento con lo que se observó, lo que se
pronosticó, el nivel de impacto, el lugar y la categoría:

  eventos/precision_pronostico.csv            todas las inundaciones completas
  eventos/precision_pronostico_depurados.csv  solo las de la selección depurada
  eventos/PRECISION.md                        resumen: cuánto acierta el pronóstico

No descarga nada: se rehace entera en cada ejecución (el workflow de eventos la corre
después de cada cruce), así que crece sola a medida que se archivan inundaciones.

    python precision_pronostico.py
"""

from __future__ import annotations

import csv
import statistics
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
EVENTOS = RAIZ / "eventos"
INUNDACIONES = EVENTOS / "inundaciones.csv"
DEPURADOS = EVENTOS / "depurados.csv"
TABLA = EVENTOS / "precision_pronostico.csv"
TABLA_DEPURADOS = EVENTOS / "precision_pronostico_depurados.csv"
RESUMEN = EVENTOS / "PRECISION.md"

# Categorías de lluvia en 24 h del documento de la SNGR (las mismas de SATI.EC): desde cuántos mm empieza cada una.
CATEGORIAS_24H = [
    (0.0, "Mínima", "Baja"),
    (0.1, "Ligera", "Baja"),
    (10.0, "Moderada", "Moderada"),
    (25.0, "Fuerte", "Moderada"),
    (50.0, "Intensa", "Alta"),
    (100.0, "Torrencial", "Muy alta"),
    (250.0, "Extrema", "Muy alta"),
]
NIVELES_ALERTA = ["Baja", "Moderada", "Alta", "Muy alta"]

# Región natural de cada provincia (INEC).
REGIONES = {
    "esmeraldas": "Costa", "manabi": "Costa", "santa elena": "Costa", "guayas": "Costa", "los rios": "Costa",
    "el oro": "Costa", "santo domingo de los tsachilas": "Costa",
    "carchi": "Sierra", "imbabura": "Sierra", "pichincha": "Sierra", "cotopaxi": "Sierra", "tungurahua": "Sierra",
    "bolivar": "Sierra", "chimborazo": "Sierra", "canar": "Sierra", "azuay": "Sierra", "loja": "Sierra",
    "sucumbios": "Amazonía", "napo": "Amazonía", "orellana": "Amazonía", "pastaza": "Amazonía",
    "morona santiago": "Amazonía", "zamora chinchipe": "Amazonía",
    "galapagos": "Insular",
}

COLUMNAS = [
    "id", "fecha", "hora", "region", "provincia", "canton", "parroquia", "sector", "latitud", "longitud",
    "nivel_impacto_sngr", "categoria_evento", "afectacion_verificada", "personas_afectadas", "viviendas_afectadas",
    "depurado",
    "observado_satelite_mm", "observado_satelite_max_5km_mm", "observado_estacion_mm", "estacion_inamhi", "estacion_distancia_km",
    "pronostico_mismo_dia_mm", "pronostico_1_dia_antes_mm", "pronostico_2_dias_antes_mm", "pronostico_max_5km_mm",
    "diferencia_mm", "relacion_pronostico_observado",
    "categoria_lluvia_observada", "categoria_lluvia_pronosticada", "acierta_categoria",
    "alerta_observada", "alerta_pronosticada", "alerta_pronosticada_moderada_o_mas",
]


def normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())


def numero(valor: str | None) -> float | None:
    try:
        return float(valor) if valor not in (None, "") else None
    except ValueError:
        return None


def categoria(mm: float | None) -> tuple[str, str] | tuple[None, None]:
    """Categoría de lluvia de 24 h y su nivel de alerta (semáforo del documento)."""
    if mm is None:
        return None, None
    elegida = CATEGORIAS_24H[0]
    for limite, nombre, alerta in CATEGORIAS_24H:
        if mm >= limite:
            elegida = (limite, nombre, alerta)
    return elegida[1], elegida[2]


def texto(valor: float | None, decimales: int = 1) -> str:
    return "" if valor is None else f"{valor:.{decimales}f}"


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo))


def fila(r: dict, depurados: set[str]) -> dict:
    # Lo observado: la lluvia del satélite el día del evento (la hay en todas); la de la estación cuando existe.
    observado = numero(r.get("lluvia_satelite_dia_evento_mm"))
    pronostico = numero(r.get("lluvia_pronosticada_mismo_dia_mm"))
    cat_obs, alerta_obs = categoria(observado)
    cat_pron, alerta_pron = categoria(pronostico)
    ambos = observado is not None and pronostico is not None
    return {
        "id": r["id"],
        "fecha": r["fecha"],
        "hora": r["hora"],
        "region": REGIONES.get(normalizar(r["provincia"]), ""),
        "provincia": r["provincia"],
        "canton": r["canton"],
        "parroquia": r["parroquia"],
        "sector": r["sector"],
        "latitud": r["latitud"],
        "longitud": r["longitud"],
        "nivel_impacto_sngr": r["nivel_sngr"],
        "categoria_evento": r["tipo_inundacion"],
        "afectacion_verificada": r["afectacion_verificada"],
        "personas_afectadas": r["personas_afectadas"],
        "viviendas_afectadas": r["viviendas_afectadas"],
        "depurado": "sí" if r["id"] in depurados else "no",
        "observado_satelite_mm": r.get("lluvia_satelite_dia_evento_mm", ""),
        "observado_satelite_max_5km_mm": r.get("lluvia_satelite_dia_evento_max_5km_mm", ""),
        "observado_estacion_mm": r.get("estacion_lluvia_medida_dia_evento_mm", ""),
        "estacion_inamhi": r.get("estacion_inamhi", ""),
        "estacion_distancia_km": r.get("estacion_inamhi_distancia_km", ""),
        "pronostico_mismo_dia_mm": r.get("lluvia_pronosticada_mismo_dia_mm", ""),
        "pronostico_1_dia_antes_mm": r.get("lluvia_pronosticada_1_dia_antes_mm", ""),
        "pronostico_2_dias_antes_mm": r.get("lluvia_pronosticada_2_dias_antes_mm", ""),
        "pronostico_max_5km_mm": r.get("lluvia_pronosticada_mismo_dia_max_5km_mm", ""),
        "diferencia_mm": texto(pronostico - observado) if ambos else "",
        "relacion_pronostico_observado": texto(pronostico / observado, 2) if ambos and observado and observado > 0 else "",
        "categoria_lluvia_observada": cat_obs or "",
        "categoria_lluvia_pronosticada": cat_pron or "",
        "acierta_categoria": ("sí" if cat_obs == cat_pron else "no") if ambos else "",
        "alerta_observada": alerta_obs or "",
        "alerta_pronosticada": alerta_pron or "",
        "alerta_pronosticada_moderada_o_mas": ("sí" if NIVELES_ALERTA.index(alerta_pron) >= 1 else "no") if alerta_pron else "",
    }


def escribir(destino: Path, filas: list[dict]) -> None:
    with open(destino, "w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS)
        escritor.writeheader()
        escritor.writerows(filas)


def metricas(filas: list[dict]) -> dict:
    pares = [(numero(f["pronostico_mismo_dia_mm"]), numero(f["observado_satelite_mm"])) for f in filas]
    pares = [(p, o) for p, o in pares if p is not None and o is not None]
    if not pares:
        return {"n": 0}
    errores = [p - o for p, o in pares]
    con_cat = [f for f in filas if f["acierta_categoria"]]
    con_alerta = [f for f in filas if f["alerta_pronosticada_moderada_o_mas"]]
    suma_obs = sum(o for _, o in pares)
    return {
        "n": len(pares),
        "obs_media": statistics.mean(o for _, o in pares),
        "pron_media": statistics.mean(p for p, _ in pares),
        "sesgo": statistics.mean(errores),
        "error_absoluto": statistics.mean(abs(e) for e in errores),
        "relacion": (sum(p for p, _ in pares) / suma_obs) if suma_obs else None,
        "acierta_categoria": sum(f["acierta_categoria"] == "sí" for f in con_cat) / len(con_cat) if con_cat else None,
        "detecta": sum(f["alerta_pronosticada_moderada_o_mas"] == "sí" for f in con_alerta) / len(con_alerta) if con_alerta else None,
    }


def renglon(nombre: str, m: dict) -> str:
    if m["n"] == 0:
        return f"| {nombre} | 0 | | | | | | | |"
    pct = lambda v: "" if v is None else f"{v * 100:.0f} %"
    rel = "" if m["relacion"] is None else f"{m['relacion']:.2f}"
    return (
        f"| {nombre} | {m['n']} | {m['obs_media']:.1f} | {m['pron_media']:.1f} | {m['sesgo']:+.1f} | "
        f"{m['error_absoluto']:.1f} | {rel} | {pct(m['acierta_categoria'])} | {pct(m['detecta'])} |"
    )


def escribir_resumen(todas: list[dict], depuradas: list[dict]) -> None:
    encabezado = [
        "| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Pronosticado / observado | Acierta categoría | Pronóstico de alerta moderada o más |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    lineas = [
        "# Precisión del pronóstico de lluvia (WRF) en las inundaciones de la SNGR",
        "",
        "Se rehace en cada cruce de eventos (`precision_pronostico.py`). Tabla por evento:",
        "`precision_pronostico.csv` (todas) y `precision_pronostico_depurados.csv` (selección depurada).",
        "",
        "- **Observado:** lluvia del satélite PERSIANN el día del evento (07:00 a 07:00, hora de Ecuador), en el lugar.",
        "  Cuando hay una estación del INAMHI a menos de 25 km, la columna `observado_estacion_mm` trae lo que midió.",
        "- **Pronosticado:** lluvia diaria del WRF (visor oficial del INAMHI) hecha el mismo día, en el lugar. Su día va",
        "  de 02:00 a 02:00, 5 h antes que el del satélite.",
        "- **Sesgo:** pronosticado − observado, en promedio (positivo = el pronóstico se pasa; negativo = se queda corto).",
        "- **Categoría:** la de lluvia en 24 h del documento de la SNGR (Mínima, Ligera, Moderada, Fuerte, Intensa,",
        "  Torrencial, Extrema). **Alerta moderada o más:** el pronóstico llegaba a 10 mm o más (lo que dispararía una alerta).",
        "",
        "## Resumen",
        "",
        *encabezado,
        renglon("Todas las inundaciones", metricas(todas)),
        renglon("Selección depurada", metricas(depuradas)),
        "",
        "## Por región",
        "",
        *encabezado,
        *[renglon(region, metricas([f for f in todas if f["region"] == region])) for region in ("Costa", "Sierra", "Amazonía", "Insular")],
        "",
        "## Por nivel de impacto de la SNGR",
        "",
        *encabezado,
        *[renglon(f"Nivel {nivel}", metricas([f for f in todas if f["nivel_impacto_sngr"] == nivel])) for nivel in sorted({f["nivel_impacto_sngr"] for f in todas if f["nivel_impacto_sngr"]})],
        "",
        "## Por categoría del evento",
        "",
        *encabezado,
        *[renglon(cat, metricas([f for f in todas if f["categoria_evento"] == cat])) for cat in sorted({f["categoria_evento"] for f in todas if f["categoria_evento"]})],
        "",
    ]
    RESUMEN.write_text("\n".join(lineas), encoding="utf-8")


def main() -> None:
    inundaciones = leer(INUNDACIONES)
    depurados = {r["id"] for r in leer(DEPURADOS)}
    filas = sorted((fila(r, depurados) for r in inundaciones), key=lambda f: (f["fecha"], f["hora"]), reverse=True)
    depuradas = [f for f in filas if f["depurado"] == "sí"]
    escribir(TABLA, filas)
    escribir(TABLA_DEPURADOS, depuradas)
    escribir_resumen(filas, depuradas)
    print(f"Precisión del pronóstico: {len(filas)} inundaciones ({len(depuradas)} depuradas)")


if __name__ == "__main__":
    main()
