#!/usr/bin/env python3
"""
Archiva la lluvia que miden las estaciones del INAMHI y la compara con el
pronóstico WRF en cada estación.

La API del INAMHI (apis.inamhi.gob.ec) solo entrega las últimas 12 h de cada
estación: si no se guardan, se pierden. Por eso el workflow corre cada 3 horas.

Resultado, en la carpeta `estaciones/`:
- `estaciones.csv`: todas las estaciones del INAMHI con código, nombre,
  coordenadas, altitud, estado y si transmiten.
- `lluvia_horaria/AAAA-MM.csv`: la lluvia de cada hora en cada estación.
- `lluvia_diaria.csv`: la lluvia de cada día de lluvia (07:00 a 07:00, hora de
  Ecuador, el mismo día que el satélite y el cruce de inundaciones).
- `pronostico_vs_medido.csv`: por estación y día del WRF (02:00 a 02:00), la
  lluvia medida y la que pronosticaba el WRF en ese punto el mismo día, 1 y 2
  días antes.

Horas: la API marca sus horas con "-05:00", pero la hora que trae es UTC (a las
08:55 de Ecuador ya entrega el dato de las "13:00"). Se guardan en UTC y en hora
de Ecuador. Cada valor es la lluvia de la hora que termina en esa hora.

Uso:
    python estaciones.py                  # descarga lo nuevo y rehace las tablas
    python estaciones.py --solo-tablas    # sin descargar: rehace las tablas con lo archivado
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CARPETA = RAIZ / "estaciones"
ESTACIONES = CARPETA / "estaciones.csv"
HORARIAS = CARPETA / "lluvia_horaria"
DIARIA = CARPETA / "lluvia_diaria.csv"
PRONOSTICO = CARPETA / "pronostico_vs_medido.csv"

API = "https://apis.inamhi.gob.ec/api/v1"
# Nemónico de la lluvia horaria (mm) en la API del INAMHI.
NEMONICO_LLUVIA = "017140801h"
GEOSERVER = "https://services.geoglows.org/geoserver"
# Recuadro del Ecuador continental para leer el WRF de una vez en todas las estaciones.
ECUADOR = {"sur": -5.1, "norte": 1.6, "oeste": -81.2, "este": -75.1}
UTC = dt.timezone.utc
ECUADOR_OFFSET = dt.timedelta(hours=-5)
HORA = dt.timedelta(hours=1)
# El día de lluvia empieza a las 07:00 de Ecuador (12:00 UTC); el del WRF, a las 02:00 (07:00 UTC).
INICIO_DIA_LLUVIA = dt.time(12)
INICIO_DIA_WRF = dt.time(7)
# Días hacia atrás que se recalculan en cada ejecución (llegan horas atrasadas).
DIAS_RECALCULO = 4

COLUMNAS_ESTACION = ["codigo", "id_estacion", "nombre", "categoria", "latitud", "longitud", "altitud_m", "estado", "transmision"]
COLUMNAS_HORARIA = ["codigo", "id_estacion", "hora_utc", "hora_ecuador", "lluvia_mm"]
COLUMNAS_DIARIA = ["codigo", "nombre", "dia_de_lluvia", "desde", "hasta", "horas_con_dato", "lluvia_mm", "completo"]
COLUMNAS_PRONOSTICO = [
    "codigo", "nombre", "dia_wrf", "desde", "hasta", "horas_con_dato", "lluvia_medida_mm", "completo",
    "pronostico_mismo_dia_mm", "pronostico_1_dia_antes_mm", "pronostico_2_dias_antes_mm",
]


# ── Utilidades ──────────────────────────────────────────────────────────


def http(url: str, intentos: int = 3, espera: float = 5.0, timeout: int = 60) -> tuple[int, bytes]:
    """GET con reintentos ante errores de red, 5xx y 429."""
    for intento in range(1, intentos + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as respuesta:
                return respuesta.status, respuesta.read()
        except urllib.error.HTTPError as error:
            if (error.code < 500 and error.code != 429) or intento == intentos:
                return error.code, error.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if intento == intentos:
                return 0, b""
        time.sleep(espera * intento)
    return 0, b""


def iso(momento: dt.datetime) -> str:
    return momento.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def hora_utc(momento: dt.datetime) -> str:
    return momento.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def hora_ecuador(momento: dt.datetime) -> str:
    return (momento.astimezone(UTC) + ECUADOR_OFFSET).strftime("%Y-%m-%d %H:%M")


def leer_hora_utc(texto: str) -> dt.datetime:
    return dt.datetime.strptime(texto, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)


def leer_csv(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8-sig", newline="") as entrada:
        return list(csv.DictReader(entrada))


def escribir_csv(ruta: Path, columnas: list[str], filas: list[dict]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: Excel reconoce las tildes al abrirlo.
    with ruta.open("w", newline="", encoding="utf-8-sig") as salida:
        escritor = csv.DictWriter(salida, fieldnames=columnas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)


def nombre_legible(texto: str) -> str:
    """'LOJA - LA ARGELIA' → 'Loja - La Argelia'."""
    minusculas = {"de", "del", "la", "las", "los", "el", "y", "en"}
    partes = []
    for parte in re.split(r"\s*-\s*", texto.strip()):
        palabras = parte.lower().split()
        partes.append(" ".join(p if i and p in minusculas else p[:1].upper() + p[1:] for i, p in enumerate(palabras)))
    return " - ".join(p for p in partes if p)


def numero(valor) -> float | None:
    try:
        n = float(valor)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


# ── API del INAMHI ──────────────────────────────────────────────────────


CATEGORIAS = {"METEOROLOGICA": "Meteorológica", "HIDROLOGICA": "Hidrológica", "HIDRO - METEOROLOGICA": "Hidrometeorológica"}


def descargar_estaciones() -> list[dict]:
    estado, cuerpo = http(f"{API}/estaciones/?captores=ELECTROMECANICA")
    if estado != 200:
        sys.exit(f"La API de estaciones del INAMHI respondió HTTP {estado}")
    filas = []
    for e in json.loads(cuerpo).get("datos", []):
        if e.get("latitud") is None or e.get("longitud") is None:
            continue
        filas.append({
            "codigo": str(e.get("codigo") or "").strip(),
            "id_estacion": e["id_estacion"],
            "nombre": nombre_legible(str(e.get("punto_obs") or "")),
            "categoria": CATEGORIAS.get(str(e.get("categoria") or "").strip().upper(), e.get("categoria")),
            "latitud": e["latitud"],
            "longitud": e["longitud"],
            "altitud_m": e.get("altitud"),
            "estado": str(e.get("estado_estacion") or "").strip().capitalize(),
            "transmision": str(e.get("estado_transmision") or "").strip().capitalize(),
        })
    return sorted(filas, key=lambda f: f["codigo"])


def descargar_horas(estacion: dict) -> list[dict]:
    """Lluvia de cada hora de las últimas 12 h de una estación ([] si no responde)."""
    url = f"{API}/datos/horarios/?" + urllib.parse.urlencode({"id_estacion": estacion["id_estacion"], "nemonico": NEMONICO_LLUVIA})
    estado, cuerpo = http(url, intentos=2)
    if estado != 200:
        return []
    filas = []
    for dato in json.loads(cuerpo).get("datos", []):
        # La hora viene marcada "-05:00" pero es UTC: se lee la hora tal cual.
        m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})", str(dato.get("fecha_toma_dato") or ""))
        valor = numero(dato.get("1h"))
        if not m:
            continue
        momento = dt.datetime.fromisoformat(m[1]).replace(tzinfo=UTC)
        filas.append({
            "codigo": estacion["codigo"],
            "id_estacion": estacion["id_estacion"],
            "hora_utc": hora_utc(momento),
            "hora_ecuador": hora_ecuador(momento),
            "lluvia_mm": "" if valor is None or valor < 0 else round(valor, 2),
        })
    return filas


def archivar_horas(estaciones: list[dict]) -> int:
    """Agrega las horas nuevas al archivo mensual. Un dato ya guardado solo se reemplaza por uno no vacío."""
    activas = [e for e in estaciones if e["transmision"] == "Transmitiendo"]
    with ThreadPoolExecutor(max_workers=6) as grupo:
        nuevas = [fila for filas in grupo.map(descargar_horas, activas) for fila in filas]
    por_mes: dict[str, list[dict]] = {}
    for fila in nuevas:
        por_mes.setdefault(fila["hora_utc"][:7], []).append(fila)
    agregadas = 0
    for mes, filas in por_mes.items():
        ruta = HORARIAS / f"{mes}.csv"
        archivo = {(f["codigo"], f["hora_utc"]): f for f in leer_csv(ruta)}
        for fila in filas:
            clave = (fila["codigo"], fila["hora_utc"])
            if clave not in archivo:
                agregadas += 1
            if clave not in archivo or fila["lluvia_mm"] != "":
                archivo[clave] = fila
        escribir_csv(ruta, COLUMNAS_HORARIA, sorted(archivo.values(), key=lambda f: (f["codigo"], f["hora_utc"])))
    print(f"{len(activas)} estaciones que transmiten · {len(nuevas)} horas recibidas · {agregadas} nuevas", flush=True)
    return agregadas


# ── Lluvia por ventana ──────────────────────────────────────────────────


def cargar_horas(desde: dt.date, hasta: dt.date) -> dict[str, dict[dt.datetime, float | None]]:
    """{código: {hora UTC: mm}} de los meses entre las dos fechas."""
    meses = sorted({(desde + dt.timedelta(days=d)).strftime("%Y-%m") for d in range((hasta - desde).days + 1)})
    horas: dict[str, dict[dt.datetime, float | None]] = {}
    for mes in meses:
        for fila in leer_csv(HORARIAS / f"{mes}.csv"):
            horas.setdefault(fila["codigo"], {})[leer_hora_utc(fila["hora_utc"])] = numero(fila["lluvia_mm"])
    return horas


def lluvia_en(horas: dict[dt.datetime, float | None], inicio: dt.datetime, cantidad: int = 24) -> tuple[int, float | None]:
    """(horas con dato, lluvia total) entre `inicio` y `inicio + cantidad` h: las horas que terminan después de inicio."""
    valores = [horas.get(inicio + HORA * (i + 1)) for i in range(cantidad)]
    con_dato = [v for v in valores if v is not None]
    return len(con_dato), (round(sum(con_dato), 1) if con_dato else None)


def lluvia_estacion_dia(horas: dict[dt.datetime, float | None], dia: dt.date) -> dict | None:
    """Lluvia del día de lluvia (07:00 a 07:00 de Ecuador) en una estación, o None sin ninguna hora con dato."""
    inicio = dt.datetime.combine(dia, INICIO_DIA_LLUVIA, UTC)
    con_dato, total = lluvia_en(horas, inicio)
    if total is None:
        return None
    return {"desde": hora_ecuador(inicio), "hasta": hora_ecuador(inicio + 24 * HORA), "horas_con_dato": con_dato, "lluvia_mm": total}


# ── Pronóstico WRF en las estaciones ────────────────────────────────────


def grilla_wrf(corrida: dt.datetime, inicio_dia: dt.datetime):
    """Lluvia diaria del WRF en todo el Ecuador continental: (oeste, sur, este, norte, filas) o None."""
    parametros = [
        ("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"), ("format", "text/plain"),
        ("coverageId", "wrf__wrf_precipitation_daily"),
        ("subset", f"Lat({ECUADOR['sur']},{ECUADOR['norte']})"), ("subset", f"Long({ECUADOR['oeste']},{ECUADOR['este']})"),
        ("subset", f'INITD("{iso(corrida)}")'), ("subset", f'time("{iso(inicio_dia)}")'),
    ]
    estado, cuerpo = http(f"{GEOSERVER}/wrf/wcs?" + urllib.parse.urlencode(parametros, safe="(),:"), timeout=120)
    texto = cuerpo.decode("utf-8", errors="replace")
    n = r"(-?[\d.]+(?:E-?\d+)?)"
    limites = re.search(rf"GeneralBounds\[\({n}, {n}\), \({n}, {n}\)\]", texto)
    if estado != 200 or not limites or "Band 0:" not in texto:
        return None
    filas = [[float(v) for v in linea.split()] for linea in texto.split("Band 0:", 1)[1].strip().splitlines() if linea.strip()]
    return (*map(float, limites.groups()), filas) if filas else None


def valor_en(grilla, lat: float, lng: float) -> float | None:
    oeste, sur, este, norte, filas = grilla
    alto, ancho = len(filas), len(filas[0])
    i = math.floor((norte - lat) / (norte - sur) * alto)
    j = math.floor((lng - oeste) / (este - oeste) * ancho)
    if not (0 <= i < alto and 0 <= j < ancho):
        return None
    valor = filas[i][j]
    return round(valor, 1) if valor >= 0 else None


def corridas_wrf() -> set[str]:
    estado, cuerpo = http(f"{GEOSERVER}/wrf/wms?service=WMS&version=1.3.0&request=GetCapabilities", timeout=120)
    xml = cuerpo.decode("utf-8", errors="replace")
    bloque = re.search(r"<Name>wrf_precipitation_daily</Name>(.*?)</Layer>", xml, re.S)
    valores = re.search(r'<Dimension name="INITD"[^>]*>([^<]*)</Dimension>', bloque.group(1)) if bloque else None
    return {re.sub(r"\.\d+Z$", ".000Z", v.strip()) for v in valores.group(1).split(",")} if valores else set()


# ── Tablas ──────────────────────────────────────────────────────────────


def rehacer_tablas(estaciones: list[dict], ahora: dt.datetime) -> None:
    """Recalcula los últimos días de la tabla diaria y de pronóstico vs. medido; lo anterior se conserva."""
    nombres = {e["codigo"]: e for e in estaciones}
    hoy = ahora.date()
    dias = [hoy - dt.timedelta(days=d) for d in range(DIAS_RECALCULO, 0, -1)]
    horas = cargar_horas(dias[0] - dt.timedelta(days=1), hoy)

    # Lluvia diaria (07:00 a 07:00): solo días ya terminados.
    diaria = {(f["codigo"], f["dia_de_lluvia"]): f for f in leer_csv(DIARIA)}
    for codigo, serie in horas.items():
        for dia in dias + [hoy]:
            inicio = dt.datetime.combine(dia, INICIO_DIA_LLUVIA, UTC)
            if inicio + 24 * HORA > ahora:
                continue
            lectura = lluvia_estacion_dia(serie, dia)
            if lectura:
                diaria[(codigo, dia.isoformat())] = {
                    "codigo": codigo, "nombre": nombres.get(codigo, {}).get("nombre", ""), "dia_de_lluvia": dia.isoformat(),
                    **lectura, "completo": "sí" if lectura["horas_con_dato"] == 24 else "no",
                }
    escribir_csv(DIARIA, COLUMNAS_DIARIA, sorted(diaria.values(), key=lambda f: (f["dia_de_lluvia"], f["codigo"]), reverse=True))

    # Pronóstico vs. medido en el día del WRF (02:00 a 02:00): el pronóstico se lee una sola vez por día.
    tabla = {(f["codigo"], f["dia_wrf"]): f for f in leer_csv(PRONOSTICO)}
    corridas = corridas_wrf()
    for dia in dias + [hoy]:
        inicio = dt.datetime.combine(dia, INICIO_DIA_WRF, UTC)
        if inicio + 24 * HORA > ahora:
            continue
        faltan = [c for c in horas if not tabla.get((c, dia.isoformat()), {}).get("pronostico_mismo_dia_mm")]
        grillas = {}
        if faltan:
            for anticipacion in (0, 1, 2):
                corrida = inicio - dt.timedelta(days=anticipacion)
                if iso(corrida) in corridas:
                    grillas[anticipacion] = grilla_wrf(corrida, inicio)
        for codigo, serie in horas.items():
            con_dato, total = lluvia_en(serie, inicio)
            if total is None:
                continue
            anterior = tabla.get((codigo, dia.isoformat()), {})
            estacion = nombres.get(codigo)
            pronostico = {}
            for anticipacion, columna in ((0, "pronostico_mismo_dia_mm"), (1, "pronostico_1_dia_antes_mm"), (2, "pronostico_2_dias_antes_mm")):
                grilla = grillas.get(anticipacion)
                calculado = valor_en(grilla, float(estacion["latitud"]), float(estacion["longitud"])) if grilla and estacion else None
                pronostico[columna] = anterior.get(columna) or ("" if calculado is None else calculado)
            tabla[(codigo, dia.isoformat())] = {
                "codigo": codigo, "nombre": estacion["nombre"] if estacion else "", "dia_wrf": dia.isoformat(),
                "desde": hora_ecuador(inicio), "hasta": hora_ecuador(inicio + 24 * HORA),
                "horas_con_dato": con_dato, "lluvia_medida_mm": total, "completo": "sí" if con_dato == 24 else "no",
                **pronostico,
            }
    escribir_csv(PRONOSTICO, COLUMNAS_PRONOSTICO, sorted(tabla.values(), key=lambda f: (f["dia_wrf"], f["codigo"]), reverse=True))
    print(f"Tablas: {len(diaria)} filas diarias · {len(tabla)} filas de pronóstico vs. medido", flush=True)


# ── Para el cruce de inundaciones ───────────────────────────────────────


def distancia_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


class LluviaEstaciones:
    """Estación del INAMHI más cercana a un punto con lluvia medida en un día de lluvia (para el cruce de inundaciones)."""

    RADIO_KM = 25
    MIN_HORAS = 18

    def __init__(self) -> None:
        self.estaciones = leer_csv(ESTACIONES)
        self.horas: dict[str, dict[dt.datetime, float | None]] = {}
        for ruta in sorted(HORARIAS.glob("*.csv")):
            for fila in leer_csv(ruta):
                self.horas.setdefault(fila["codigo"], {})[leer_hora_utc(fila["hora_utc"])] = numero(fila["lluvia_mm"])

    def cercana(self, lat: float, lng: float, dia: dt.date) -> dict | None:
        candidatas = []
        for e in self.estaciones:
            serie = self.horas.get(e["codigo"])
            if not serie:
                continue
            distancia = distancia_km(lat, lng, float(e["latitud"]), float(e["longitud"]))
            if distancia > self.RADIO_KM:
                continue
            lectura = lluvia_estacion_dia(serie, dia)
            if lectura and lectura["horas_con_dato"] >= self.MIN_HORAS:
                candidatas.append((distancia, e, lectura))
        if not candidatas:
            return None
        distancia, e, lectura = min(candidatas, key=lambda c: c[0])
        return {
            "que_es": "Lluvia que midió el pluviómetro de la estación del INAMHI más cercana (a menos de 25 km) en el día "
                      "del evento, de 07:00 a 07:00 (hora de Ecuador). Es lluvia medida en tierra, más exacta que el "
                      "satélite en ese punto, pero puede no representar el lugar del evento si la estación está lejos.",
            "estacion": {"codigo": e["codigo"], "nombre": e["nombre"], "distancia_km": round(distancia, 1),
                         "latitud": float(e["latitud"]), "longitud": float(e["longitud"])},
            "dia_del_evento": lectura,
        }


# ── Principal ───────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Archiva la lluvia de las estaciones del INAMHI y la compara con el WRF.")
    parser.add_argument("--solo-tablas", action="store_true", help="no descarga: rehace las tablas con lo ya archivado")
    args = parser.parse_args()
    ahora = dt.datetime.now(UTC)

    if args.solo_tablas:
        estaciones = leer_csv(ESTACIONES)
    else:
        estaciones = descargar_estaciones()
        escribir_csv(ESTACIONES, COLUMNAS_ESTACION, estaciones)
        archivar_horas(estaciones)
    rehacer_tablas(estaciones, ahora)
    return 0


if __name__ == "__main__":
    sys.exit(main())
