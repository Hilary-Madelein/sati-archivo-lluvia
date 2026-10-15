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
- `pronostico_por_estacion.csv`: el pronóstico puntual de lluvia en cada una de
  las 186 estaciones, día por día desde el 1 de enero de 2026: lo que
  pronosticaba el WRF en las coordenadas de la estación para cada día del WRF
  (02:00 a 02:00), hecho el mismo día, 1 y 2 días antes; y, desde que se
  archiva la estación, la lluvia que midió en esas mismas 24 h.

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
PRONOSTICO = CARPETA / "pronostico_por_estacion.csv"
# Primer día del pronóstico puntual por estación (el WRF tiene corridas desde nov 2025).
DESDE_PRONOSTICO = dt.date(2026, 1, 1)

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
    "codigo", "nombre", "latitud", "longitud", "dia_wrf", "desde", "hasta",
    "pronostico_mismo_dia_mm", "pronostico_1_dia_antes_mm", "pronostico_2_dias_antes_mm",
    "lluvia_medida_mm", "horas_con_dato", "medicion_completa",
]
# Anticipación de la corrida (días) → columna.
ANTICIPACIONES = ((0, "pronostico_mismo_dia_mm"), (1, "pronostico_1_dia_antes_mm"), (2, "pronostico_2_dias_antes_mm"))


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
        # Sin coordenadas reales (vienen en 0, 0) o de prueba ("Pruebas 1"): no sirven para el pronóstico puntual.
        if e.get("latitud") is None or e.get("longitud") is None or (e["latitud"] == 0 and e["longitud"] == 0):
            continue
        if "prueba" in str(e.get("punto_obs") or "").lower():
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

    print(f"Tabla diaria: {len(diaria)} filas", flush=True)
    rehacer_pronostico(estaciones, horas, ahora, dias)


def rehacer_pronostico(estaciones: list[dict], horas: dict, ahora: dt.datetime, dias_recalculo: list[dt.date], max_dias: int = 400) -> None:
    """
    Pronóstico puntual por estación: para cada día del WRF desde DESDE_PRONOSTICO
    que ya terminó, el valor del WRF en las coordenadas de cada estación (una
    descarga de todo el Ecuador por corrida, no una por estación). Cada día se
    calcula una sola vez; la lluvia medida de los últimos días se actualiza.
    """
    # Solo las estaciones vigentes de la lista (si el INAMHI quita una, sale de la tabla).
    vigentes = {e["codigo"] for e in estaciones}
    tabla = {(f["codigo"], f["dia_wrf"]): f for f in leer_csv(PRONOSTICO) if f["codigo"] in vigentes}
    # Último día del WRF ya terminado: el día D va de D 07:00 UTC a D+1 07:00 UTC.
    ultimo = (ahora - dt.timedelta(hours=INICIO_DIA_WRF.hour)).date() - dt.timedelta(days=1)
    dias = [DESDE_PRONOSTICO + dt.timedelta(days=d) for d in range((ultimo - DESDE_PRONOSTICO).days + 1)]
    # Los más recientes primero: si una ejecución no alcanza, lo nuevo nunca queda atrás.
    faltan = [dia for dia in reversed(dias) if any((e["codigo"], dia.isoformat()) not in tabla for e in estaciones)]
    corridas = corridas_wrf() if faltan else set()

    calculados = 0
    for dia in faltan[:max_dias]:
        inicio = dt.datetime.combine(dia, INICIO_DIA_WRF, UTC)
        grillas = {}
        for anticipacion, _ in ANTICIPACIONES:
            corrida = inicio - dt.timedelta(days=anticipacion)
            if iso(corrida) in corridas:
                grillas[anticipacion] = grilla_wrf(corrida, inicio)
        if any(grilla is None for grilla in grillas.values()):
            print(f"  {dia}: el servidor del WRF no respondió; se reintenta en la próxima ejecución", flush=True)
            continue
        for e in estaciones:
            lat, lng = float(e["latitud"]), float(e["longitud"])
            fila = {
                "codigo": e["codigo"], "nombre": e["nombre"], "latitud": lat, "longitud": lng,
                "dia_wrf": dia.isoformat(), "desde": hora_ecuador(inicio), "hasta": hora_ecuador(inicio + 24 * HORA),
            }
            for anticipacion, columna in ANTICIPACIONES:
                valor = valor_en(grillas[anticipacion], lat, lng) if anticipacion in grillas else None
                fila[columna] = "" if valor is None else valor
            tabla[(e["codigo"], dia.isoformat())] = {**tabla.get((e["codigo"], dia.isoformat()), {}), **fila}
        calculados += 1
        if calculados % 30 == 0:
            print(f"  pronóstico por estación: {calculados}/{min(len(faltan), max_dias)} días", flush=True)

    # Lluvia medida en la misma ventana del WRF, para los días recientes (las horas se archivan desde oct 2026).
    for dia in dias_recalculo + [ahora.date()]:
        inicio = dt.datetime.combine(dia, INICIO_DIA_WRF, UTC)
        for codigo, serie in horas.items():
            fila = tabla.get((codigo, dia.isoformat()))
            if not fila:
                continue
            con_dato, total = lluvia_en(serie, inicio)
            if total is not None:
                fila.update({"lluvia_medida_mm": total, "horas_con_dato": con_dato, "medicion_completa": "sí" if con_dato == 24 else "no"})

    escribir_csv(PRONOSTICO, COLUMNAS_PRONOSTICO, sorted(tabla.values(), key=lambda f: (f["dia_wrf"], f["codigo"]), reverse=True))
    print(f"Pronóstico por estación: {calculados} días nuevos · {len(tabla)} filas", flush=True)



# ── Para el cruce de inundaciones ───────────────────────────────────────


def distancia_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


class LluviaEstaciones:
    """
    Para el cruce de inundaciones: la estación del INAMHI más cercana a un punto
    (a menos de 25 km), con la lluvia que midió el día del evento y el pronóstico
    puntual del WRF en la estación para ese día.
    """

    RADIO_KM = 25
    MIN_HORAS = 18

    def __init__(self) -> None:
        self.estaciones = leer_csv(ESTACIONES)
        self.horas: dict[str, dict[dt.datetime, float | None]] = {}
        for ruta in sorted(HORARIAS.glob("*.csv")):
            for fila in leer_csv(ruta):
                self.horas.setdefault(fila["codigo"], {})[leer_hora_utc(fila["hora_utc"])] = numero(fila["lluvia_mm"])
        self.pronostico = {(f["codigo"], f["dia_wrf"]): f for f in leer_csv(PRONOSTICO)}

    def cercana(self, lat: float, lng: float, dia: dt.date, momento: dt.datetime | None = None) -> dict | None:
        candidatas = sorted(
            ((distancia_km(lat, lng, float(e["latitud"]), float(e["longitud"])), e) for e in self.estaciones),
            key=lambda c: c[0],
        )
        candidatas = [(d, e) for d, e in candidatas if d <= self.RADIO_KM]
        if not candidatas:
            return None
        # La más cercana que midió ese día; si ninguna midió, la más cercana (para su pronóstico).
        medidas = []
        for distancia, e in candidatas:
            lectura = lluvia_estacion_dia(self.horas.get(e["codigo"], {}), dia)
            if lectura and lectura["horas_con_dato"] >= self.MIN_HORAS:
                medidas.append((distancia, e, lectura))
        distancia, e, medida = medidas[0] if medidas else (*candidatas[0], None)

        fila = self.pronostico.get((e["codigo"], dia.isoformat()))
        pronostico = None
        if fila:
            pronostico = {"desde": fila["desde"], "hasta": fila["hasta"]}
            for columna, clave in (("pronostico_mismo_dia_mm", "hecho_el_mismo_dia_mm"),
                                   ("pronostico_1_dia_antes_mm", "hecho_1_dia_antes_mm"),
                                   ("pronostico_2_dias_antes_mm", "hecho_2_dias_antes_mm")):
                pronostico[clave] = numero(fila.get(columna))
            pronostico["lluvia_medida_mm"] = numero(fila.get("lluvia_medida_mm"))
            if all(pronostico[k] is None for k in ("hecho_el_mismo_dia_mm", "hecho_1_dia_antes_mm", "hecho_2_dias_antes_mm")):
                pronostico = None
        # Lo que midió en las 1, 3, 6 y 24 h hasta el evento (incluida la hora en que ocurrió).
        antes = None
        serie = self.horas.get(e["codigo"], {})
        if momento is not None and serie:
            fin = momento.astimezone(UTC).replace(minute=0, second=0, microsecond=0) + HORA
            antes = {}
            for n in (1, 3, 6, 24):
                con_dato, total = lluvia_en(serie, fin - n * HORA, n)
                antes[f"ultimas_{n}_h"] = (
                    {"desde": hora_ecuador(fin - n * HORA), "hasta": hora_ecuador(fin), "horas_con_dato": con_dato, "lluvia_mm": total}
                    if total is not None and con_dato >= math.ceil(0.8 * n) else None
                )
            if not any(antes.values()):
                antes = None
        if medida is None and pronostico is None:
            return None
        return {
            "que_es": "Estación del INAMHI más cercana al evento (a menos de 25 km). 'lluvia_medida_dia_del_evento' es lo "
                      "que midió su pluviómetro de 07:00 a 07:00 (hora de Ecuador; hay mediciones desde oct 2026) y "
                      "'lluvia_medida_antes_del_evento', lo que midió en la última hora, 3, 6 y 24 h hasta el evento. "
                      "'pronostico_puntual' es lo que el WRF pronosticaba en las coordenadas de la estación para el día "
                      "del WRF (02:00 a 02:00), hecho el mismo día, 1 y 2 días antes, y lo que midió la estación en esas "
                      "mismas 24 h, si hay.",
            "estacion": {"codigo": e["codigo"], "nombre": e["nombre"], "distancia_km": round(distancia, 1),
                         "latitud": float(e["latitud"]), "longitud": float(e["longitud"])},
            "lluvia_medida_dia_del_evento": medida,
            "lluvia_medida_antes_del_evento": antes,
            "pronostico_puntual": pronostico,
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
