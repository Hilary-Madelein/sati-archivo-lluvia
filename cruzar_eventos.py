#!/usr/bin/env python3
"""
Cruza cada inundación registrada por la SNGR con la lluvia y el caudal de ese
lugar y ese día, y archiva solo las que tienen los dos datos.

Para cada inundación guarda:
- El evento tal como lo registra la SNGR (lugar, fecha, nivel, afectaciones…).
- Lluvia medida por satélite (PERSIANN, INAMHI) el día del evento y los dos
  anteriores, en el lugar y la más alta a menos de 5 km. Hay datos desde 2025.
- Caudal del río más cercano (GEOGLOWS): el de ese día, cuántas veces su caudal
  normal y qué crecida alcanzó (la de 2, 5, 10… años).
- Si existen: la lluvia que pronosticaba el WRF del INAMHI para ese día (desde
  nov 2025) y el caudal que pronosticaba GEOGLOWS (últimos ~2 meses).

El "día de lluvia" del evento va de las 07:00 a las 07:00 del día siguiente
(hora de Ecuador), como el acumulado diario del satélite. Un evento de
madrugada (antes de las 07:00) cuenta en el día de lluvia anterior.

Resultado, en la carpeta `eventos/`:
- `inundaciones/AAAA/MM/<id>.json`: un archivo por inundación completa.
- `inundaciones.csv`: una fila por inundación completa (se abre en Excel).
- `pendientes/AAAA/MM/<id>.json`: esperan algún dato (la simulación del río va
  ~1 mes atrasada); se completan solas en un cruce posterior.
- `descartados.csv`: las que nunca podrán tener los dos datos, y por qué.
- `RESUMEN.md`: cuántas hay de cada tipo.

Credenciales de la SNGR: variables de entorno SNGR_USUARIO y SNGR_CLAVE
(en GitHub, como secretos del repositorio). Solo usa la biblioteca estándar.

Uso:
    python cruzar_eventos.py                         # últimos 30 días (lo que hace el workflow a diario)
    python cruzar_eventos.py --desde 2018-01-01      # histórico completo, por tandas (--max-eventos)
    python cruzar_eventos.py --solo-archivo          # sin la SNGR: solo pendientes y formato antiguo
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import statistics
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CARPETA = RAIZ / "eventos" / "inundaciones"
PENDIENTES = RAIZ / "eventos" / "pendientes"
TABLA = RAIZ / "eventos" / "inundaciones.csv"
DESCARTADOS = RAIZ / "eventos" / "descartados.csv"
RESUMEN = RAIZ / "eventos" / "RESUMEN.md"
# Versión del formato de los JSON: los de una versión anterior se vuelven a cruzar.
VERSION = 2

SNGR_LOGIN = os.environ.get("SNGR_LOGIN_URL", "https://monitoreocoe.gestionderiesgos.gob.ec/api/usuarios/login")
SNGR_EVENTOS = os.environ.get("SNGR_EVENTS_URL", "https://monitoreocoe.gestionderiesgos.gob.ec/api/public/eventos_lluvias")
GEOSERVER = "https://services.geoglows.org/geoserver"
GEOGLOWS = "https://geoglows.ecmwf.int/api/v2"

# Eventos de inundación del Catálogo Nacional de la SNGR (los mismos que SATI.EC).
INUNDACIONES = {"inundacion", "inundacion costera", "inundacion fluvial", "inundacion lacustre", "inundacion pluvial"}
ECUADOR = (-6.0, 2.5, -92.5, -75.0)  # sur, norte, oeste, este (incluye Galápagos)
RADIO_ZONA = 0.045  # ~5 km: "la más alta a menos de 5 km"
PERIODOS = (2, 5, 10, 25, 50, 100)
# Cada cuánto se reintenta un evento pendiente (la simulación de GEOGLOWS se actualiza ~1 vez al mes).
REINTENTO_PENDIENTES = dt.timedelta(days=3)
# Tras tantos intentos fallidos por errores de las fuentes, el evento se descarta.
MAX_INTENTOS = 10
# Primer día con lluvia por satélite (PERSIANN) en el servidor del INAMHI.
INICIO_SATELITE = dt.date(2025, 1, 1)
# El día de lluvia empieza a esta hora de Ecuador (12:00 UTC), como el PERSIANN de 24 h.
HORA_DIA_LLUVIA = 7
DESDE_RETORNO = 1980
UTC = dt.timezone.utc
ECUADOR_OFFSET = dt.timedelta(hours=-5)


# ── Utilidades ──────────────────────────────────────────────────────────


def http(url: str, datos: dict | None = None, intentos: int = 3, espera: float = 8.0, timeout: int = 120) -> tuple[int, bytes]:
    """GET (o POST JSON si hay `datos`) con reintentos ante errores de red, 5xx y 429 (demasiadas consultas)."""
    for intento in range(1, intentos + 1):
        try:
            cuerpo = json.dumps(datos).encode() if datos is not None else None
            pedido = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": "application/json"} if cuerpo else {})
            with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
                return respuesta.status, respuesta.read()
        except urllib.error.HTTPError as error:
            if (error.code < 500 and error.code != 429) or intento == intentos:
                return error.code, error.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if intento == intentos:
                return 0, b""
        time.sleep(espera * intento)
    return 0, b""


def normalizar(texto: str) -> str:
    """'Inundación ' → 'inundacion' (como SATI.EC)."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes.lower()).strip()


def numero(valor) -> float | None:
    try:
        n = float(valor)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def cantidad(valor) -> int:
    n = numero(valor)
    return round(n) if n and n > 0 else 0


def fecha_iso(valor) -> str | None:
    """'2/9/2026' (día/mes/año) o '2026-09-02' → '2026-09-02'."""
    texto = str(valor or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", texto) or None
    if m:
        a, mes, d = int(m[1]), int(m[2]), int(m[3])
    elif m2 := re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", texto):
        a, mes, d = int(m2[3]), int(m2[2]), int(m2[1])
    else:
        return None
    try:
        return dt.date(a, mes, d).isoformat()
    except ValueError:
        return None


def hora(valor) -> str:
    m = re.match(r"^(\d{1,2}):(\d{1,2})", str(valor or "").strip())
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        return "00:00"
    return f"{int(m[1]):02d}:{int(m[2]):02d}"


def json_js(valor) -> str:
    """JSON como JSON.stringify de JavaScript (para el mismo identificador que SATI.EC)."""
    if isinstance(valor, list):
        return "[" + ",".join(json_js(v) for v in valor) + "]"
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return json.dumps(valor, ensure_ascii=False)


def iso(momento: dt.datetime) -> str:
    return momento.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ── SNGR ────────────────────────────────────────────────────────────────


class Sngr:
    def __init__(self) -> None:
        self.usuario = os.environ.get("SNGR_USUARIO", "")
        self.clave = os.environ.get("SNGR_CLAVE", "")
        if not self.usuario or not self.clave:
            sys.exit("Faltan SNGR_USUARIO y SNGR_CLAVE (en GitHub: Settings → Secrets and variables → Actions → Secrets).")
        self.token: str | None = None

    def _login(self) -> str:
        estado, cuerpo = http(SNGR_LOGIN, {"usuario": self.usuario, "clave": self.clave}, intentos=2)
        datos = json.loads(cuerpo or b"{}")
        if estado != 200 or not datos.get("token"):
            sys.exit(f"La SNGR rechazó el inicio de sesión (HTTP {estado}). Revisa los secretos SNGR_USUARIO y SNGR_CLAVE.")
        return datos["token"]

    def eventos(self, desde: dt.date, hasta: dt.date) -> list[dict]:
        for intento in range(2):
            self.token = self.token or self._login()
            estado, cuerpo = http(SNGR_EVENTOS, {"token": self.token, "fecha_ini": desde.isoformat(), "fecha_fin": hasta.isoformat()}, intentos=2, timeout=180)
            datos = json.loads(cuerpo or b"{}") if cuerpo else {}
            if estado in (401, 403) or datos.get("success") is False:
                self.token = None  # sesión vencida: se renueva una vez
                continue
            if estado != 200 or not isinstance(datos.get("data"), list):
                raise RuntimeError(f"SNGR respondió HTTP {estado} para {desde}…{hasta}")
            return datos["data"]
        raise RuntimeError("La SNGR rechazó la sesión dos veces")


def a_evento(r: dict) -> dict | None:
    """Registro de la SNGR → evento de inundación (o None si no es inundación o no es válido)."""
    if normalizar(re.sub(r"\(.*?\)", " ", str(r.get("Evento") or ""))) not in INUNDACIONES:
        return None
    fecha = fecha_iso(r.get("FechaDelEvento"))
    lat, lng = numero(r.get("Latitud")), numero(r.get("Longitud"))
    if (lat is None or lng is None) and r.get("Coordenadas"):
        partes = str(r["Coordenadas"]).split(",")
        lat, lng = (numero(partes[0]), numero(partes[1])) if len(partes) == 2 else (None, None)
    if not fecha or lat is None or lng is None:
        return None
    sur, norte, oeste, este = ECUADOR
    if not (sur <= lat <= norte and oeste <= lng <= este):
        return None
    h = hora(r.get("HoraDelEvento"))
    parroquia = (r.get("CodificacionParroquial") or "").strip() or normalizar(str(r.get("Parroquia") or ""))
    identificador = hashlib.sha256(
        json_js([parroquia, normalizar(str(r.get("Evento") or "")), fecha, h, lat, lng]).encode()
    ).hexdigest()[:32]
    nivel = re.search(r"\d+", str(r.get("NivelDelEvento") or ""))
    texto = lambda clave: (str(r.get(clave)).strip() or None) if r.get(clave) is not None else None  # noqa: E731
    return {
        "id": identificador,
        "tipo": texto("Evento"),
        "fecha": fecha,
        "hora": h,
        "provincia": texto("Provincia"),
        "canton": texto("Canton"),
        "parroquia": texto("Parroquia"),
        "sector": texto("Comunidad/Barrio/Sector"),
        "latitud": lat,
        "longitud": lng,
        "nivel": int(nivel[0]) if nivel else None,
        "estado": texto("EstadoDelEvento"),
        "descripcion": texto("DescripcionGeneralDeEvento"),
        "personas_afectadas": cantidad(r.get("PersonasAfectadasDirectamente")),
        "viviendas_afectadas": cantidad(r.get("ViviendasAfectadas")),
        "personas_evacuadas": cantidad(r.get("PersonasEvacuadas")),
        "personas_fallecidas": cantidad(r.get("PersonasFallecidas")),
    }



# ── Horarios ────────────────────────────────────────────────────────────


def hora_ecuador(momento: dt.datetime) -> str:
    return (momento.astimezone(UTC) + ECUADOR_OFFSET).strftime("%Y-%m-%d %H:%M")


def periodo(inicio: dt.datetime, horas: int = 24) -> dict:
    """Desde y hasta, en hora de Ecuador."""
    return {"desde": hora_ecuador(inicio), "hasta": hora_ecuador(inicio + dt.timedelta(hours=horas))}


def dia_de_lluvia(evento: dict) -> dt.date:
    """Día de lluvia (07:00 a 07:00) en el que ocurrió el evento: de madrugada cuenta el anterior."""
    fecha = dt.date.fromisoformat(evento["fecha"])
    return fecha - dt.timedelta(days=1) if int(evento["hora"][:2]) < HORA_DIA_LLUVIA else fecha


def inicio_dia_lluvia(dia: dt.date) -> dt.datetime:
    """07:00 de Ecuador de ese día, en UTC."""
    return dt.datetime.combine(dia, dt.time(HORA_DIA_LLUVIA), UTC) - ECUADOR_OFFSET


# ── Lluvia (GeoServer del INAMHI) ───────────────────────────────────────


def grilla_texto(espacio: str, capa: str, lat: float, lng: float, subconjuntos: list[str]) -> list[tuple[float, float, float]] | None:
    """Celdas (lat, lng, valor) alrededor del punto, pedidas en texto plano al WCS (sin librerías)."""
    margen = RADIO_ZONA + 0.05
    parametros = [
        ("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"), ("format", "text/plain"),
        ("coverageId", f"{espacio}__{capa}"),
        ("subset", f"Lat({lat - margen:.4f},{lat + margen:.4f})"), ("subset", f"Long({lng - margen:.4f},{lng + margen:.4f})"),
    ] + [("subset", s) for s in subconjuntos]
    estado, cuerpo = http(f"{GEOSERVER}/{espacio}/wcs?" + urllib.parse.urlencode(parametros, safe="(),:"), intentos=3)
    texto = cuerpo.decode("utf-8", errors="replace")
    # Cerca de la línea ecuatorial los límites vienen en notación científica (2.86E-8).
    n = r"(-?[\d.]+(?:E-?\d+)?)"
    limites = re.search(rf"GeneralBounds\[\({n}, {n}\), \({n}, {n}\)\]", texto)
    if estado != 200 or not limites or "Band 0:" not in texto:
        return None
    oeste, sur, este, norte = map(float, limites.groups())
    filas = [[float(v) for v in linea.split()] for linea in texto.split("Band 0:", 1)[1].strip().splitlines() if linea.strip()]
    if not filas:
        return None
    alto, ancho = len(filas), len(filas[0])
    return [
        (norte - (i + 0.5) * (norte - sur) / alto, oeste + (j + 0.5) * (este - oeste) / ancho, valor)
        for i, fila in enumerate(filas)
        for j, valor in enumerate(fila)
    ]


def leer_punto(celdas, lat: float, lng: float) -> dict | None:
    """Lluvia de la celda del lugar y la más alta a menos de 5 km. Los negativos (sin dato) no cuentan."""
    if not celdas:
        return None
    validas = [(la, lo, v) for la, lo, v in celdas if v >= 0]
    if not validas:
        return None
    cercana = min(validas, key=lambda c: (c[0] - lat) ** 2 + (c[1] - lng) ** 2)
    zona = [v for la, lo, v in validas if (la - lat) ** 2 + (lo - lng) ** 2 <= RADIO_ZONA**2] or [cercana[2]]
    return {"en_el_lugar_mm": round(cercana[2], 1), "maxima_a_menos_de_5km_mm": round(max(zona), 1)}


def lluvia_satelite(dia: dt.date, lat: float, lng: float, disponibles: set[str]) -> dict | None:
    """
    PERSIANN 24 h del día de lluvia del evento y de los dos anteriores (None si falta alguno).
    La capa diaria fechada D 00:00 UTC acumula de las 12:00 UTC del día anterior a las 12:00 UTC
    de D, es decir, de 07:00 a 07:00 de Ecuador (comprobado sumando la capa horaria).
    """
    resultado: dict = {
        "que_es": "Lluvia que cayó según el satélite PERSIANN (servidor del INAMHI), en milímetros. Cada día va "
                  "de las 07:00 a las 07:00 del día siguiente (hora de Ecuador). 'en_el_lugar' es la celda (~4 km) "
                  "donde ocurrió el evento; 'maxima_a_menos_de_5km', la celda más lluviosa alrededor. El satélite "
                  "suele quedarse corto en aguaceros fuertes y cortos.",
    }
    grillas = []
    for atras, nombre in ((2, "dos_dias_antes"), (1, "dia_anterior"), (0, "dia_del_evento")):
        inicio = inicio_dia_lluvia(dia - dt.timedelta(days=atras))
        etiqueta = iso(dt.datetime.combine(inicio.date() + dt.timedelta(days=1), dt.time(0), UTC))
        if etiqueta not in disponibles:
            return None
        celdas = grilla_texto("satellite_based_precipitation", "persiann_pdir_24h", lat, lng, [f'time("{etiqueta}")'])
        lectura = leer_punto(celdas, lat, lng)
        if lectura is None:
            return None
        grillas.append(celdas)
        resultado[nombre] = {**periodo(inicio), **lectura}
    # Total de los 3 días celda por celda: la más alta del total, no la suma de las más altas.
    if len({len(g) for g in grillas}) == 1:
        total = [
            (la, lo, sum(g[i][2] for g in grillas) if all(g[i][2] >= 0 for g in grillas) else -1.0)
            for i, (la, lo, _) in enumerate(grillas[0])
        ]
        lectura = leer_punto(total, lat, lng)
    else:
        dias = [resultado[n] for n in ("dos_dias_antes", "dia_anterior", "dia_del_evento")]
        lectura = {k: round(sum(d[k] for d in dias), 1) for k in ("en_el_lugar_mm", "maxima_a_menos_de_5km_mm")}
    resultado["total_3_dias"] = {**periodo(inicio_dia_lluvia(dia - dt.timedelta(days=2)), 72), **lectura}
    # El día del evento primero.
    return {k: resultado[k] for k in ("que_es", "dia_del_evento", "dia_anterior", "dos_dias_antes", "total_3_dias")}


def lluvia_pronosticada(dia: dt.date, lat: float, lng: float, corridas: set[str]) -> dict | None:
    """WRF diario: lo que pronosticaban para el día del evento las corridas del mismo día, de 1 y de 2 días antes."""
    # El día del WRF (visor oficial) son las 24 h que empiezan a las 07:00 UTC (02:00 de Ecuador).
    inicio = dt.datetime.combine(dia, dt.time(7), UTC)
    resultado: dict = {
        "que_es": "Lluvia que el modelo WRF del INAMHI pronosticaba para el día del evento (la del visor oficial), "
                  "en milímetros, según el pronóstico hecho ese mismo día, 1 y 2 días antes. Su día va de 02:00 a "
                  "02:00 (hora de Ecuador), 5 h antes que el del satélite.",
        "periodo": periodo(inicio),
    }
    for anticipacion, nombre in ((0, "hecho_el_mismo_dia"), (1, "hecho_1_dia_antes"), (2, "hecho_2_dias_antes")):
        corrida = inicio - dt.timedelta(days=anticipacion)
        if iso(corrida) not in corridas:
            continue
        celdas = grilla_texto("wrf", "wrf_precipitation_daily", lat, lng, [f'INITD("{iso(corrida)}")', f'time("{iso(inicio)}")'])
        lectura = leer_punto(celdas, lat, lng)
        if lectura:
            resultado[nombre] = {"corrida_del_modelo": hora_ecuador(corrida), **lectura}
    return resultado if len(resultado) > 2 else None


def dimension(espacio: str, capa: str, nombre: str) -> set[str]:
    """Valores de una dimensión (time, INITD) según el GetCapabilities."""
    estado, cuerpo = http(f"{GEOSERVER}/{espacio}/wms?service=WMS&version=1.3.0&request=GetCapabilities")
    xml = cuerpo.decode("utf-8", errors="replace")
    bloque = re.search(rf"<Name>{re.escape(capa)}</Name>(.*?)</Layer>", xml, re.S)
    valores = re.search(rf'<Dimension name="{nombre}"[^>]*>([^<]*)</Dimension>', bloque.group(1)) if bloque else None
    return {v.strip() for v in valores.group(1).split(",")} if valores else set()


# ── Caudal (GEOGLOWS) ───────────────────────────────────────────────────


class Rios:
    """Río más cercano, simulación histórica y periodos de retorno, con caché por río."""

    def __init__(self) -> None:
        self.simulaciones: dict[int, dict] = {}
        self.cerrojo = threading.Lock()
        self.fechas_api: set[str] = set()
        estado, cuerpo = http(f"{GEOGLOWS}/dates?format=json")
        if estado == 200:
            self.fechas_api = {d[:8] for d in json.loads(cuerpo).get("dates", [])}

    def rio_cercano(self, lat: float, lng: float) -> int | None:
        estado, cuerpo = http(f"{GEOGLOWS}/getriverid?lat={lat:.5f}&lon={lng:.5f}&format=json", intentos=4)
        try:
            return int(json.loads(cuerpo)["river_id"]) if estado == 200 else None
        except (ValueError, KeyError, TypeError):
            return None

    def simulacion(self, rio: int) -> dict | None:
        """Caudal diario simulado desde 1980, periodos de retorno (Gumbel, como el Hydroviewer del INAMHI) y caudal normal de cada mes."""
        with self.cerrojo:
            if rio in self.simulaciones:
                return self.simulaciones[rio]
        estado, cuerpo = http(f"{GEOGLOWS}/retrospectivedaily/{rio}?format=json&start_date={DESDE_RETORNO}0101", intentos=4, timeout=180)
        if estado != 200:
            return None  # sin caché: un error pasajero no afecta a los demás eventos del mismo río
        datos = json.loads(cuerpo)
        serie = datos.get(str(rio)) or []
        caudales = {f[:10]: numero(v) for f, v in zip(datos.get("datetime", []), serie)}
        validos = {f: v for f, v in caudales.items() if v is not None}
        maximos: dict[str, float] = {}
        por_mes: dict[str, list[float]] = {}
        for fecha, valor in validos.items():
            maximos[fecha[:4]] = max(maximos.get(fecha[:4], 0.0), valor)
            por_mes.setdefault(fecha[5:7], []).append(valor)
        anuales = list(maximos.values())
        if len(anuales) < 2:
            return None
        media = sum(anuales) / len(anuales)
        desviacion = math.sqrt(sum((x - media) ** 2 for x in anuales) / (len(anuales) - 1))
        retorno = {
            t: round(media - (math.sqrt(6) / math.pi) * (0.5772 + math.log(math.log(t / (t - 1)))) * desviacion, 1)
            for t in PERIODOS
        }
        resultado = {
            "caudales": validos,
            "retorno": retorno,
            "normal_por_mes": {mes: statistics.median(valores) for mes, valores in por_mes.items()},
            "hasta": max(validos),
        }
        with self.cerrojo:
            self.simulaciones[rio] = resultado
        return resultado

    def pronostico(self, rio: int, dia: dt.date) -> dict:
        """Lo que pronosticaban para el día de lluvia del evento y el siguiente las corridas de ese día y de 1 y 2 días antes (la API guarda ~2 meses)."""
        salida = {}
        inicio = inicio_dia_lluvia(dia)
        fin = inicio + dt.timedelta(days=2)
        for anticipacion, nombre in ((0, "hecho_el_mismo_dia"), (1, "hecho_1_dia_antes"), (2, "hecho_2_dias_antes")):
            corrida = dia - dt.timedelta(days=anticipacion)
            if corrida.strftime("%Y%m%d") not in self.fechas_api:
                continue
            estado, cuerpo = http(f"{GEOGLOWS}/forecaststats/{rio}?format=json&date={corrida:%Y%m%d}", intentos=3)
            if estado != 200:
                continue
            datos = json.loads(cuerpo)
            del_periodo = [
                i for i, t in enumerate(datos.get("datetime", []))
                if inicio <= dt.datetime.fromisoformat(t.replace("Z", "+00:00")) < fin
            ]
            maximo = lambda clave: max((v for i in del_periodo if (v := numero(datos.get(clave, [None] * (i + 1))[i])) is not None), default=None)  # noqa: E731
            salida[nombre] = {
                "corrida_del_modelo": corrida.isoformat(),
                "maximo_promedio_de_ensambles_m3s": maximo("flow_avg"),
                "maximo_del_ensamble_mas_alto_m3s": maximo("flow_max"),
                "maximo_alta_resolucion_m3s": maximo("high_res"),
            }
        return salida


def numero_es(valor: float) -> str:
    """12.34 → '12,3'."""
    return f"{valor:.1f}".replace(".", ",")


def caudal(lat: float, lng: float, dia: dt.date, rios: Rios) -> tuple[dict | None, str | None, str]:
    """(datos, qué falta, por qué falta: 'espera' | 'fallo' | 'definitivo')."""
    rio = rios.rio_cercano(lat, lng)
    if rio is None:
        return None, "caudal: GEOGLOWS no encontró el río más cercano", "fallo"
    simulacion = rios.simulacion(rio)
    if simulacion is None:
        return None, "caudal: GEOGLOWS no respondió", "fallo"
    dias = (dia.isoformat(), (dia + dt.timedelta(days=1)).isoformat())
    if simulacion["hasta"] < dias[1]:
        return None, f"caudal: la simulación de GEOGLOWS llega hasta el {simulacion['hasta']} y se actualiza ~1 vez al mes", "espera"
    caudales = [simulacion["caudales"].get(d) for d in dias]
    if None in caudales:
        return None, "caudal: la simulación no tiene dato para esos días", "definitivo"

    pico = max(caudales)
    normal = simulacion["normal_por_mes"].get(dias[0][5:7])
    umbrales = simulacion["retorno"]
    superados = [t for t in PERIODOS if pico >= umbrales[t]]
    crecida = max(superados) if superados else 0
    datos = {
        "que_es": "Caudal del río más cercano al evento según el modelo GEOGLOWS (simulación diaria), en m³/s. "
                  "'caudal_normal_del_mes' es la mediana de ese mes desde 1980. Los umbrales de crecida son los caudales "
                  "que el río alcanza en promedio una vez cada 2, 5, 10… años: superar el de 2 años ya es una crecida.",
        "rio_geoglows": rio,
        "caudal_dia_del_evento_m3s": round(caudales[0], 1),
        "caudal_maximo_ese_dia_y_el_siguiente_m3s": round(pico, 1),
        "caudal_normal_del_mes_m3s": round(normal, 1) if normal else None,
        "veces_el_caudal_normal": round(pico / normal, 1) if normal else None,
        "umbrales_de_crecida_m3s": {f"cada_{t}_años": umbrales[t] for t in PERIODOS},
        "crecida_alcanzada_años": crecida,
        "crecida_alcanzada": (
            f"Superó la crecida de {crecida} años ({numero_es(umbrales[crecida])} m³/s)"
            if crecida else f"Ninguna: no llegó a la crecida de 2 años ({numero_es(umbrales[2])} m³/s)"
        ),
    }
    pronostico = rios.pronostico(rio, dia)
    if pronostico:
        datos["caudal_pronosticado"] = {
            "que_es": "Caudal máximo que pronosticaba GEOGLOWS para el día del evento y el siguiente, según el pronóstico "
                      "hecho ese día, 1 y 2 días antes: promedio de los 51 ensambles, el ensamble más alto y la corrida "
                      "de alta resolución.",
            **pronostico,
        }
    return datos, None, ""


# ── Cruce ───────────────────────────────────────────────────────────────


def resumen(registro: dict) -> str:
    """Una o dos líneas para leer el cruce de un vistazo."""
    partes = []
    if s := registro.get("lluvia_satelite"):
        dia, total = s["dia_del_evento"], s["total_3_dias"]
        partes.append(
            f"Satélite: {numero_es(dia['en_el_lugar_mm'])} mm el día del evento en el lugar "
            f"(hasta {numero_es(dia['maxima_a_menos_de_5km_mm'])} mm a menos de 5 km) y "
            f"{numero_es(total['en_el_lugar_mm'])} mm en 3 días."
        )
    if p := registro.get("lluvia_pronosticada"):
        valores = [
            f"{numero_es(p[clave]['en_el_lugar_mm'])} mm ({texto})"
            for clave, texto in (("hecho_2_dias_antes", "2 días antes"), ("hecho_1_dia_antes", "1 día antes"), ("hecho_el_mismo_dia", "el mismo día"))
            if clave in p
        ]
        partes.append("Pronóstico WRF para ese día: " + ", ".join(valores) + ".")
    if c := registro.get("caudal_del_rio"):
        veces = f", {numero_es(c['veces_el_caudal_normal'])} veces su caudal normal" if c.get("veces_el_caudal_normal") is not None else ""
        crecida = c["crecida_alcanzada"]
        partes.append(f"Río: {numero_es(c['caudal_maximo_ese_dia_y_el_siguiente_m3s'])} m³/s{veces}; {crecida[0].lower()}{crecida[1:]}.")
    return " ".join(partes)


def procesar(evento: dict, rios: Rios, persiann: set[str], corridas_wrf: set[str]) -> tuple[dict, str]:
    """Cruza un evento. Devuelve el registro y su estado: 'completo' | 'espera' | 'fallo' | 'definitivo'."""
    dia = dia_de_lluvia(evento)
    lat, lng = evento["latitud"], evento["longitud"]
    falta, motivos = [], set()

    satelite = lluvia_satelite(dia, lat, lng, persiann)
    if satelite is None:
        reciente = (dt.date.today() - dia).days <= 10
        falta.append("lluvia por satélite: aún no publicada" if reciente else "lluvia por satélite: sin dato en ese lugar")
        motivos.add("espera" if reciente else "definitivo")
    rio, motivo, tipo = caudal(lat, lng, dia, rios)
    if motivo:
        falta.append(motivo)
        motivos.add(tipo)

    registro = {
        "version": VERSION,
        "evento": evento,
        "resumen": "",
        "dia_de_lluvia": {"fecha": dia.isoformat(), **periodo(inicio_dia_lluvia(dia))},
        "lluvia_satelite": satelite,
        "lluvia_pronosticada": lluvia_pronosticada(dia, lat, lng, corridas_wrf),
        "caudal_del_rio": rio,
        "cruce": {"completo": not falta, "falta": falta, "fallos": 0, "procesado": iso(dt.datetime.now(UTC))},
    }
    registro["resumen"] = resumen(registro)
    estado = "completo" if not falta else next(m for m in ("definitivo", "fallo", "espera") if m in motivos)
    return registro, estado


# ── Archivo ─────────────────────────────────────────────────────────────


def ruta(carpeta: Path, evento: dict) -> Path:
    return carpeta / evento["fecha"][:4] / evento["fecha"][5:7] / f"{evento['id']}.json"


def guardar(carpeta: Path, registro: dict) -> None:
    archivo = ruta(carpeta, registro["evento"])
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    otra = ruta(PENDIENTES if carpeta == CARPETA else CARPETA, registro["evento"])
    otra.unlink(missing_ok=True)


def leer_registros(carpeta: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in carpeta.rglob("*.json")]


COLUMNAS_DESCARTE = ["id", "fecha", "hora", "provincia", "canton", "parroquia", "motivo"]


def leer_descartados() -> dict[str, dict]:
    if not DESCARTADOS.exists():
        return {}
    with DESCARTADOS.open(encoding="utf-8-sig", newline="") as entrada:
        return {f["id"]: f for f in csv.DictReader(entrada)}


def escribir_csv(destino: Path, columnas: list[str], filas: list[dict]) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: Excel reconoce las tildes al abrirlo.
    with destino.open("w", newline="", encoding="utf-8-sig") as salida:
        escritor = csv.DictWriter(salida, fieldnames=columnas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)


def fila(registro: dict) -> dict:
    """Una inundación completa como fila del CSV."""
    e, s, p, c = registro["evento"], registro["lluvia_satelite"], registro.get("lluvia_pronosticada") or {}, registro["caudal_del_rio"]
    q = c.get("caudal_pronosticado", {})
    leer = lambda d, k: (d or {}).get(k)  # noqa: E731
    return {
        "id": e["id"], "fecha": e["fecha"], "hora": e["hora"], "provincia": e["provincia"], "canton": e["canton"],
        "parroquia": e["parroquia"], "sector": e["sector"], "latitud": e["latitud"], "longitud": e["longitud"],
        "nivel_sngr": e["nivel"], "estado_sngr": e["estado"],
        "personas_afectadas": e["personas_afectadas"], "viviendas_afectadas": e["viviendas_afectadas"],
        "personas_evacuadas": e["personas_evacuadas"], "personas_fallecidas": e["personas_fallecidas"],
        "dia_de_lluvia": registro["dia_de_lluvia"]["fecha"],
        "lluvia_satelite_dia_evento_mm": s["dia_del_evento"]["en_el_lugar_mm"],
        "lluvia_satelite_dia_evento_max_5km_mm": s["dia_del_evento"]["maxima_a_menos_de_5km_mm"],
        "lluvia_satelite_dia_anterior_mm": s["dia_anterior"]["en_el_lugar_mm"],
        "lluvia_satelite_dos_dias_antes_mm": s["dos_dias_antes"]["en_el_lugar_mm"],
        "lluvia_satelite_3_dias_mm": s["total_3_dias"]["en_el_lugar_mm"],
        "lluvia_satelite_3_dias_max_5km_mm": s["total_3_dias"]["maxima_a_menos_de_5km_mm"],
        "lluvia_pronosticada_mismo_dia_mm": leer(p.get("hecho_el_mismo_dia"), "en_el_lugar_mm"),
        "lluvia_pronosticada_1_dia_antes_mm": leer(p.get("hecho_1_dia_antes"), "en_el_lugar_mm"),
        "lluvia_pronosticada_2_dias_antes_mm": leer(p.get("hecho_2_dias_antes"), "en_el_lugar_mm"),
        "rio_geoglows": c["rio_geoglows"],
        "caudal_dia_evento_m3s": c["caudal_dia_del_evento_m3s"],
        "caudal_max_dia_evento_y_siguiente_m3s": c["caudal_maximo_ese_dia_y_el_siguiente_m3s"],
        "caudal_normal_del_mes_m3s": c["caudal_normal_del_mes_m3s"],
        "veces_el_caudal_normal": c["veces_el_caudal_normal"],
        "crecida_alcanzada_años": c["crecida_alcanzada_años"],
        **{f"umbral_crecida_{t}_años_m3s": c["umbrales_de_crecida_m3s"][f"cada_{t}_años"] for t in PERIODOS},
        "caudal_pronosticado_mismo_dia_m3s": leer(q.get("hecho_el_mismo_dia"), "maximo_promedio_de_ensambles_m3s"),
        "caudal_pronosticado_1_dia_antes_m3s": leer(q.get("hecho_1_dia_antes"), "maximo_promedio_de_ensambles_m3s"),
        "resumen": registro["resumen"],
        "descripcion_sngr": e["descripcion"],
    }


def tabla_md(encabezado: tuple[str, str], filas) -> list[str]:
    return [f"| {encabezado[0]} | {encabezado[1]} |", "|---|---:|", *(f"| {a} | {b} |" for a, b in filas), ""]


def escribir_resumen(completos: list[dict], pendientes: list[dict], descartados: dict[str, dict], por_cruzar: int) -> None:
    """eventos/RESUMEN.md: cuántas inundaciones hay de cada tipo."""
    motivos = Counter(f["motivo"] for f in descartados.values())
    por_mes = Counter(r["evento"]["fecha"][:7] for r in completos)
    provincias = Counter(r["evento"]["provincia"] or "Sin provincia" for r in completos)
    crecidas = Counter(r["caudal_del_rio"]["crecida_alcanzada_años"] for r in completos)
    rangos = ((0, 5, "Menos de 5 mm"), (5, 20, "5 a 20 mm"), (20, 50, "20 a 50 mm"), (50, math.inf, "50 mm o más"))
    lluvia = Counter(
        next(texto for minimo, maximo, texto in rangos if minimo <= r["lluvia_satelite"]["dia_del_evento"]["maxima_a_menos_de_5km_mm"] < maximo)
        for r in completos
    )
    con_pron_lluvia = sum(1 for r in completos if r.get("lluvia_pronosticada"))
    con_pron_caudal = sum(1 for r in completos if r["caudal_del_rio"].get("caudal_pronosticado"))

    lineas = [
        "# Inundaciones de la SNGR cruzadas con lluvia y caudal",
        "",
        f"Actualizado el {dt.date.today():%Y-%m-%d}. Se genera solo en cada cruce; ver el README para qué tiene cada archivo.",
        "",
        *tabla_md(("Inundaciones", "Cantidad"), [
            ("**Completas**: con lluvia por satélite y caudal del río (`inundaciones/`, `inundaciones.csv`)", f"**{len(completos)}**"),
            ("…de ellas, con el pronóstico de lluvia del WRF para ese día", con_pron_lluvia),
            ("…de ellas, con el pronóstico de caudal de GEOGLOWS para ese día", con_pron_caudal),
            ("Pendientes: esperan un dato que llegará (`pendientes/`)", len(pendientes)),
            *([("Por volver a cruzar con el formato nuevo (próximas ejecuciones)", por_cruzar)] if por_cruzar else []),
            ("Descartadas: nunca tendrán los dos datos (`descartados.csv`)", len(descartados)),
        ]),
    ]
    if motivos:
        lineas += ["## Descartadas, por motivo", "", *tabla_md(("Motivo", "Inundaciones"), motivos.most_common())]
    if completos:
        lineas += [
            "## Completas, según la crecida que alcanzó el río", "",
            *tabla_md(("Crecida (caudal simulado)", "Inundaciones"), [
                ("Ninguna (no llegó a la de 2 años)" if t == 0 else f"Superó la de {t} años", crecidas[t]) for t in (0, *PERIODOS) if crecidas[t]
            ]),
            "## Completas, según la lluvia del día del evento", "",
            "La más alta a menos de 5 km medida por el satélite.", "",
            *tabla_md(("Lluvia", "Inundaciones"), [(texto, lluvia[texto]) for _, _, texto in rangos]),
            "## Completas, por mes", "",
            *tabla_md(("Mes", "Inundaciones"), sorted(por_mes.items(), reverse=True)),
            "## Completas, por provincia", "",
            *tabla_md(("Provincia", "Inundaciones"), provincias.most_common()),
        ]
    RESUMEN.write_text("\n".join(lineas), encoding="utf-8")


def meses(desde: dt.date, hasta: dt.date):
    """Rangos de consulta a la SNGR, de a un mes."""
    inicio = desde
    while inicio <= hasta:
        siguiente = (inicio.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        yield inicio, min(siguiente - dt.timedelta(days=1), hasta)
        inicio = siguiente


def main() -> int:
    hoy = dt.date.today()
    parser = argparse.ArgumentParser(description="Cruza las inundaciones de la SNGR con lluvia y caudal, y las archiva.")
    parser.add_argument("--desde", type=dt.date.fromisoformat, default=hoy - dt.timedelta(days=30))
    parser.add_argument("--hasta", type=dt.date.fromisoformat, default=hoy)
    parser.add_argument("--max-eventos", type=int, default=1500, help="tope de eventos a procesar en esta ejecución")
    parser.add_argument("--hilos", type=int, default=4)
    parser.add_argument("--registros", type=Path, help="prueba: lee registros crudos de la SNGR de un archivo JSON en vez de consultar la API")
    parser.add_argument("--solo-archivo", action="store_true", help="no consulta la SNGR: solo vuelve a cruzar los pendientes y los de formato antiguo")
    args = parser.parse_args()

    # Lo ya archivado: completos y pendientes (de cualquier fecha: los pendientes se reintentan aunque sean antiguos).
    archivados: dict[str, dict] = {r["evento"]["id"]: r for carpeta in (CARPETA, PENDIENTES) for r in leer_registros(carpeta)}
    descartados = leer_descartados()

    eventos: dict[str, dict] = {}
    if args.registros:
        for registro in json.loads(args.registros.read_text(encoding="utf-8")):
            evento = a_evento(registro)
            if evento and args.desde.isoformat() <= evento["fecha"] <= args.hasta.isoformat():
                eventos[evento["id"]] = evento
    elif not args.solo_archivo:
        sngr = Sngr()
        for inicio, fin in meses(args.desde, args.hasta):
            for registro in sngr.eventos(inicio, fin):
                evento = a_evento(registro)
                if evento:
                    eventos[evento["id"]] = evento
            print(f"SNGR {inicio:%Y-%m}: {len(eventos)} inundaciones acumuladas", flush=True)
    for identificador, registro in archivados.items():
        eventos.setdefault(identificador, registro["evento"])

    def descartar(evento: dict, motivo: str) -> None:
        descartados[evento["id"]] = {**{k: evento.get(k) for k in COLUMNAS_DESCARTE}, "motivo": motivo}
        for carpeta in (CARPETA, PENDIENTES):
            ruta(carpeta, evento).unlink(missing_ok=True)
        archivados.pop(evento["id"], None)

    # Nuevos, pendientes que toca reintentar y los de formato antiguo; los completos solo actualizan los datos de la SNGR.
    por_procesar, actualizados = [], 0
    ahora = dt.datetime.now(UTC)
    for evento in eventos.values():
        if evento["id"] in descartados:
            continue
        if dia_de_lluvia(evento) - dt.timedelta(days=2) < INICIO_SATELITE:
            descartar(evento, "lluvia por satélite: no hay datos antes de 2025")
            continue
        registro = archivados.get(evento["id"])
        if registro and registro.get("version") == VERSION:
            ultimo = dt.datetime.fromisoformat(registro["cruce"]["procesado"].replace("Z", "+00:00"))
            if registro["cruce"]["completo"] or ahora - ultimo < REINTENTO_PENDIENTES:
                if registro["evento"] != evento:
                    registro["evento"] = evento
                    guardar(CARPETA if registro["cruce"]["completo"] else PENDIENTES, registro)
                    actualizados += 1
                continue
        por_procesar.append(evento)
    por_procesar.sort(key=lambda e: e["fecha"], reverse=True)
    tanda = por_procesar[: args.max_eventos]
    print(f"{len(eventos)} inundaciones · {len(por_procesar)} por cruzar (esta vez {len(tanda)}) · {actualizados} actualizadas", flush=True)

    persiann = {re.sub(r"\.\d+Z$", ".000Z", v) for v in dimension("satellite_based_precipitation", "persiann_pdir_24h", "time")}
    corridas_wrf = {re.sub(r"\.\d+Z$", ".000Z", v) for v in dimension("wrf", "wrf_precipitation_daily", "INITD")}
    rios = Rios()

    hechos = Counter()
    with ThreadPoolExecutor(max_workers=args.hilos) as grupo:
        tareas = {grupo.submit(procesar, evento, rios, persiann, corridas_wrf): evento for evento in tanda}
        for tarea in as_completed(tareas):
            evento = tareas[tarea]
            try:
                registro, estado = tarea.result()
            except Exception as error:  # un evento con problemas no detiene el resto
                print(f"  {evento['fecha']} {evento['id'][:8]}: error ({error})", flush=True)
                continue
            anterior = archivados.get(evento["id"], {})
            fallos = anterior.get("cruce", {}).get("fallos", 0) if anterior.get("version") == VERSION else 0
            registro["cruce"]["fallos"] = fallos + (estado == "fallo")
            if estado == "completo":
                guardar(CARPETA, registro)
            elif estado == "definitivo" or registro["cruce"]["fallos"] >= MAX_INTENTOS:
                descartar(evento, "; ".join(registro["cruce"]["falta"]))
                estado = "descartado"
            else:
                guardar(PENDIENTES, registro)
            if estado != "descartado":
                archivados[evento["id"]] = registro
            hechos[estado] += 1
            if sum(hechos.values()) % 50 == 0:
                print(f"  {sum(hechos.values())}/{len(tanda)} cruzados", flush=True)

    completos = [r for r in leer_registros(CARPETA) if r.get("version") == VERSION]
    pendientes = [r for r in leer_registros(PENDIENTES) if r.get("version") == VERSION]
    completos.sort(key=lambda r: (r["evento"]["fecha"], r["evento"]["hora"]), reverse=True)
    escribir_csv(TABLA, list(fila(completos[0]).keys()) if completos else ["id"], [fila(r) for r in completos])
    escribir_csv(DESCARTADOS, COLUMNAS_DESCARTE, sorted(descartados.values(), key=lambda f: f["fecha"] or "", reverse=True))
    por_cruzar = sum(1 for r in archivados.values() if r.get("version") != VERSION)
    escribir_resumen(completos, pendientes, descartados, por_cruzar)
    print(f"Esta vez: {dict(hechos)}")
    print(f"Listo: {len(completos)} inundaciones completas · {len(pendientes)} pendientes · {len(descartados)} descartadas"
          + (f" · {por_cruzar} por volver a cruzar (vuelve a ejecutar)" if por_cruzar else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
