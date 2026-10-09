#!/usr/bin/env python3
"""
Cruza cada inundación registrada por la SNGR con la lluvia y el caudal de ese
lugar y ese día, y lo archiva.

Para cada evento guarda:
- El evento tal como lo registra la SNGR (lugar, fecha, nivel, afectaciones…).
- Lluvia observada por satélite (PERSIANN, INAMHI): el día del evento y los dos
  anteriores, en el punto y la máxima en ~5 km. Hay datos desde enero de 2025.
- Lluvia pronosticada (WRF del INAMHI) para ese día por las corridas del mismo
  día, de 1 y de 2 días antes. Hay datos desde noviembre de 2025.
- Río más cercano (GEOGLOWS): caudal simulado ese día, periodos de retorno de
  2 a 100 años (Gumbel, 1980–hoy) y cuál superó; y, si el evento es de los
  últimos ~2 meses, lo que pronosticaban las corridas de ese día y de 1 y 2 días antes.

Resultado, en la carpeta `eventos/`:
- `inundaciones/AAAA/MM/<id>.json`: un archivo por evento, con todo el detalle.
- `inundaciones.csv`: una fila por evento (se abre en Excel).

Las fuentes que aún no tienen datos para un evento (p. ej. la simulación del
río, que va ~1 mes atrasada) se marcan como pendientes y se completan en un
archivado posterior.

Credenciales de la SNGR: variables de entorno SNGR_USUARIO y SNGR_CLAVE
(en GitHub, como secretos del repositorio). Solo usa la biblioteca estándar.

Uso:
    python cruzar_eventos.py                         # últimos 30 días (lo que hace el workflow a diario)
    python cruzar_eventos.py --desde 2018-01-01      # histórico completo, por tandas (--max-eventos)
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
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CARPETA = RAIZ / "eventos" / "inundaciones"
TABLA = RAIZ / "eventos" / "inundaciones.csv"

SNGR_LOGIN = os.environ.get("SNGR_LOGIN_URL", "https://monitoreocoe.gestionderiesgos.gob.ec/api/usuarios/login")
SNGR_EVENTOS = os.environ.get("SNGR_EVENTS_URL", "https://monitoreocoe.gestionderiesgos.gob.ec/api/public/eventos_lluvias")
GEOSERVER = "https://services.geoglows.org/geoserver"
GEOGLOWS = "https://geoglows.ecmwf.int/api/v2"

# Eventos de inundación del Catálogo Nacional de la SNGR (los mismos que SATI.EC).
INUNDACIONES = {"inundacion", "inundacion costera", "inundacion fluvial", "inundacion lacustre", "inundacion pluvial"}
ECUADOR = (-6.0, 2.5, -92.5, -75.0)  # sur, norte, oeste, este (incluye Galápagos)
RADIO_ZONA = 0.045  # ~5 km: "máximo en la zona"
PERIODOS = (2, 5, 10, 25, 50, 100)
# Cada cuánto se reintenta un evento con fuentes pendientes (la simulación de GEOGLOWS se actualiza ~1 vez al mes).
REINTENTO_PENDIENTES = dt.timedelta(days=3)
DESDE_RETORNO = 1980
UTC = dt.timezone.utc
ECUADOR_OFFSET = dt.timedelta(hours=-5)


# ── Utilidades ──────────────────────────────────────────────────────────


def http(url: str, datos: dict | None = None, intentos: int = 3, espera: float = 8.0, timeout: int = 120) -> tuple[int, bytes]:
    """GET (o POST JSON si hay `datos`) con reintentos ante errores de red y 5xx."""
    for intento in range(1, intentos + 1):
        try:
            cuerpo = json.dumps(datos).encode() if datos is not None else None
            pedido = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": "application/json"} if cuerpo else {})
            with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
                return respuesta.status, respuesta.read()
        except urllib.error.HTTPError as error:
            if error.code < 500 or intento == intentos:
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


# ── Lluvia (GeoServer del INAMHI) ───────────────────────────────────────


def grilla_texto(espacio: str, capa: str, lat: float, lng: float, subconjuntos: list[str]) -> list[tuple[float, float, float]] | None:
    """Celdas (lat, lng, valor) alrededor del punto, pedidas en texto plano al WCS (sin librerías)."""
    margen = RADIO_ZONA + 0.05
    parametros = [
        ("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"), ("format", "text/plain"),
        ("coverageId", f"{espacio}__{capa}"),
        ("subset", f"Lat({lat - margen:.4f},{lat + margen:.4f})"), ("subset", f"Long({lng - margen:.4f},{lng + margen:.4f})"),
    ] + [("subset", s) for s in subconjuntos]
    estado, cuerpo = http(f"{GEOSERVER}/{espacio}/wcs?" + urllib.parse.urlencode(parametros, safe="(),:"), intentos=2)
    texto = cuerpo.decode("utf-8", errors="replace")
    limites = re.search(r"GeneralBounds\[\(([-\d.]+), ([-\d.]+)\), \(([-\d.]+), ([-\d.]+)\)\]", texto)
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
    """Valor de la celda más cercana y máximo en ~5 km. Los negativos (sin dato) no cuentan."""
    if not celdas:
        return None
    validas = [(la, lo, v) for la, lo, v in celdas if v >= 0]
    if not validas:
        return None
    cercana = min(validas, key=lambda c: (c[0] - lat) ** 2 + (c[1] - lng) ** 2)
    zona = [v for la, lo, v in validas if (la - lat) ** 2 + (lo - lng) ** 2 <= RADIO_ZONA**2] or [cercana[2]]
    return {"punto_mm": round(cercana[2], 1), "max_5km_mm": round(max(zona), 1)}


def lluvia_observada(dia: dt.date, lat: float, lng: float, disponibles: set[str]) -> dict:
    """PERSIANN 24 h del día del evento y de los dos anteriores."""
    resultado: dict = {"fuente": "PERSIANN (satélite), servidor del INAMHI", "dias": {}}
    for atras, nombre in ((0, "dia_evento"), (1, "dia_anterior"), (2, "dos_dias_antes")):
        momento = dt.datetime.combine(dia - dt.timedelta(days=atras), dt.time(0), UTC)
        if iso(momento) not in disponibles:
            resultado["dias"][nombre] = None
            continue
        celdas = grilla_texto("satellite_based_precipitation", "persiann_pdir_24h", lat, lng, [f'time("{iso(momento)}")'])
        resultado["dias"][nombre] = leer_punto(celdas, lat, lng)
    valores = list(resultado["dias"].values())
    if all(v is not None for v in valores):
        resultado["acumulado_72h"] = {
            "punto_mm": round(sum(v["punto_mm"] for v in valores), 1),
            "max_5km_mm": round(sum(v["max_5km_mm"] for v in valores), 1),
        }
    resultado["disponible"] = any(v is not None for v in valores)
    return resultado


def lluvia_pronosticada(dia: dt.date, lat: float, lng: float, corridas: set[str]) -> dict:
    """WRF diario: lo que pronosticaban para el día del evento las corridas del mismo día, de 1 y de 2 días antes."""
    resultado: dict = {"fuente": "WRF del INAMHI (lluvia diaria del visor oficial)", "por_corrida": []}
    # El día del evento en el WRF: las 24 h que empiezan a las 07:00 UTC (02:00 de Ecuador).
    inicio_dia = dt.datetime.combine(dia, dt.time(7), UTC)
    for anticipacion in (0, 1, 2):
        corrida = inicio_dia - dt.timedelta(days=anticipacion)
        if iso(corrida) not in corridas:
            continue
        celdas = grilla_texto("wrf", "wrf_precipitation_daily", lat, lng, [f'INITD("{iso(corrida)}")', f'time("{iso(inicio_dia)}")'])
        lectura = leer_punto(celdas, lat, lng)
        if lectura:
            resultado["por_corrida"].append({"anticipacion_dias": anticipacion, "corrida": iso(corrida), **lectura})
    resultado["disponible"] = bool(resultado["por_corrida"])
    return resultado


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
        self.simulaciones: dict[int, dict | None] = {}
        self.cerrojo = threading.Lock()
        self.fechas_api: set[str] = set()
        estado, cuerpo = http(f"{GEOGLOWS}/dates?format=json")
        if estado == 200:
            self.fechas_api = {d[:8] for d in json.loads(cuerpo).get("dates", [])}

    def rio_cercano(self, lat: float, lng: float) -> int | None:
        estado, cuerpo = http(f"{GEOGLOWS}/getriverid?lat={lat:.5f}&lon={lng:.5f}&format=json", intentos=2)
        try:
            return int(json.loads(cuerpo)["river_id"]) if estado == 200 else None
        except (ValueError, KeyError, TypeError):
            return None

    def simulacion(self, rio: int) -> dict | None:
        """Caudal diario simulado desde 1980 y periodos de retorno (Gumbel, como el Hydroviewer del INAMHI)."""
        with self.cerrojo:
            if rio in self.simulaciones:
                return self.simulaciones[rio]
        estado, cuerpo = http(f"{GEOGLOWS}/retrospectivedaily/{rio}?format=json&start_date={DESDE_RETORNO}0101", intentos=2, timeout=180)
        resultado = None
        if estado == 200:
            datos = json.loads(cuerpo)
            serie = datos.get(str(rio)) or []
            caudales = {f[:10]: numero(v) for f, v in zip(datos.get("datetime", []), serie)}
            maximos: dict[str, float] = {}
            for fecha, valor in caudales.items():
                if valor is not None:
                    maximos[fecha[:4]] = max(maximos.get(fecha[:4], 0.0), valor)
            anuales = list(maximos.values())
            if len(anuales) >= 2:
                media = sum(anuales) / len(anuales)
                desviacion = math.sqrt(sum((x - media) ** 2 for x in anuales) / (len(anuales) - 1))
                retorno = {
                    str(t): round(media - (math.sqrt(6) / math.pi) * (0.5772 + math.log(math.log(t / (t - 1)))) * desviacion, 1)
                    for t in PERIODOS
                }
                resultado = {"caudales": caudales, "retorno": retorno, "hasta": max(caudales)}
        with self.cerrojo:
            self.simulaciones[rio] = resultado
        return resultado

    def pronostico(self, rio: int, dia: dt.date) -> list[dict]:
        """Corridas del mismo día y de 1 y 2 días antes (solo las que sirve la API, ~2 meses): máximos del día del evento."""
        salida = []
        inicio = dt.datetime.combine(dia, dt.time(0), UTC) - ECUADOR_OFFSET  # 00:00 de Ecuador en UTC
        fin = inicio + dt.timedelta(days=1)
        for anticipacion in (0, 1, 2):
            corrida = (dia - dt.timedelta(days=anticipacion)).strftime("%Y%m%d")
            if corrida not in self.fechas_api:
                continue
            estado, cuerpo = http(f"{GEOGLOWS}/forecaststats/{rio}?format=json&date={corrida}", intentos=2)
            if estado != 200:
                continue
            datos = json.loads(cuerpo)
            del_dia = [
                i for i, t in enumerate(datos.get("datetime", []))
                if inicio <= dt.datetime.fromisoformat(t.replace("Z", "+00:00")) < fin
            ]
            maximo = lambda clave: max((v for i in del_dia if (v := numero(datos.get(clave, [None] * (i + 1))[i])) is not None), default=None)  # noqa: E731
            salida.append({
                "anticipacion_dias": anticipacion,
                "corrida": corrida,
                "max_promedio_ensamble_m3s": maximo("flow_avg"),
                "max_ensamble_m3s": maximo("flow_max"),
                "max_alta_resolucion_m3s": maximo("high_res"),
            })
        return salida


def caudal(evento: dict, dia: dt.date, rios: Rios) -> dict:
    resultado: dict = {"fuente": "GEOGLOWS (río más cercano al punto del evento)"}
    rio = rios.rio_cercano(evento["latitud"], evento["longitud"])
    resultado["river_id"] = rio
    if rio is None:
        resultado["disponible"] = False
        return resultado
    simulacion = rios.simulacion(rio)
    if simulacion:
        valor = simulacion["caudales"].get(dia.isoformat())
        resultado["periodos_retorno_m3s"] = simulacion["retorno"]
        resultado["caudal_simulado_dia_m3s"] = round(valor, 2) if valor is not None else None
        resultado["simulacion_hasta"] = simulacion["hasta"]
        if valor is not None:
            superados = [int(t) for t, q in simulacion["retorno"].items() if valor >= q]
            resultado["supera_periodo_anos"] = max(superados) if superados else 0
    resultado["pronostico_para_ese_dia"] = rios.pronostico(rio, dia)
    resultado["disponible"] = simulacion is not None
    return resultado


# ── Archivo ─────────────────────────────────────────────────────────────


def ruta(evento: dict) -> Path:
    return CARPETA / evento["fecha"][:4] / evento["fecha"][5:7] / f"{evento['id']}.json"


def pendientes(registro: dict) -> list[str]:
    """Fuentes que aún pueden completarse en un archivado posterior."""
    dia = dt.date.fromisoformat(registro["evento"]["fecha"])
    faltan = []
    rio = registro.get("rio", {})
    if rio.get("river_id") and rio.get("caudal_simulado_dia_m3s") is None and (not rio.get("simulacion_hasta") or rio["simulacion_hasta"] < dia.isoformat()):
        faltan.append("caudal simulado (la simulación de GEOGLOWS aún no llega a esa fecha)")
    if dia >= dt.date(2025, 1, 1) and not registro.get("lluvia_observada", {}).get("acumulado_72h") and (dt.date.today() - dia).days < 10:
        faltan.append("lluvia observada (el satélite aún no publica algún día)")
    return faltan


def procesar(evento: dict, rios: Rios, persiann: set[str], corridas_wrf: set[str]) -> dict:
    dia = dt.date.fromisoformat(evento["fecha"])
    lat, lng = evento["latitud"], evento["longitud"]
    registro = {
        "evento": evento,
        "lluvia_observada": lluvia_observada(dia, lat, lng, persiann),
        "lluvia_pronosticada": lluvia_pronosticada(dia, lat, lng, corridas_wrf),
        "rio": caudal(evento, dia, rios),
        "procesado": iso(dt.datetime.now(UTC)),
    }
    registro["pendiente"] = pendientes(registro)
    return registro


COLUMNAS = [
    "id", "fecha", "hora", "tipo", "provincia", "canton", "parroquia", "sector", "latitud", "longitud", "nivel", "estado",
    "personas_afectadas", "viviendas_afectadas", "personas_evacuadas", "personas_fallecidas",
    "lluvia_obs_dia_mm", "lluvia_obs_dia_max5km_mm", "lluvia_obs_dia_anterior_mm", "lluvia_obs_72h_mm", "lluvia_obs_72h_max5km_mm",
    "lluvia_pron_mismo_dia_mm", "lluvia_pron_1dia_antes_mm", "lluvia_pron_2dias_antes_mm", "lluvia_pron_max5km_mm",
    "river_id", "caudal_simulado_m3s", "supera_periodo_anos", "q2_m3s", "q5_m3s", "q10_m3s", "q25_m3s", "q50_m3s", "q100_m3s",
    "caudal_pron_mismo_dia_max_promedio_m3s", "caudal_pron_1dia_antes_max_promedio_m3s",
    "pendiente", "descripcion",
]


def fila(registro: dict) -> dict:
    e, obs, pron, rio = registro["evento"], registro["lluvia_observada"], registro["lluvia_pronosticada"], registro["rio"]
    dias = obs.get("dias", {})
    por_anticipacion = {c["anticipacion_dias"]: c for c in pron.get("por_corrida", [])}
    caudal_pron = {c["anticipacion_dias"]: c for c in rio.get("pronostico_para_ese_dia", [])}
    retorno = rio.get("periodos_retorno_m3s", {})
    leer = lambda d, k: d.get(k) if d else None  # noqa: E731
    return {
        **{k: e.get(k) for k in COLUMNAS if k in e},
        "lluvia_obs_dia_mm": leer(dias.get("dia_evento"), "punto_mm"),
        "lluvia_obs_dia_max5km_mm": leer(dias.get("dia_evento"), "max_5km_mm"),
        "lluvia_obs_dia_anterior_mm": leer(dias.get("dia_anterior"), "punto_mm"),
        "lluvia_obs_72h_mm": leer(obs.get("acumulado_72h"), "punto_mm"),
        "lluvia_obs_72h_max5km_mm": leer(obs.get("acumulado_72h"), "max_5km_mm"),
        "lluvia_pron_mismo_dia_mm": leer(por_anticipacion.get(0), "punto_mm"),
        "lluvia_pron_1dia_antes_mm": leer(por_anticipacion.get(1), "punto_mm"),
        "lluvia_pron_2dias_antes_mm": leer(por_anticipacion.get(2), "punto_mm"),
        "lluvia_pron_max5km_mm": max((c["max_5km_mm"] for c in por_anticipacion.values()), default=None),
        "river_id": rio.get("river_id"),
        "caudal_simulado_m3s": rio.get("caudal_simulado_dia_m3s"),
        "supera_periodo_anos": rio.get("supera_periodo_anos"),
        **{f"q{t}_m3s": retorno.get(str(t)) for t in PERIODOS},
        "caudal_pron_mismo_dia_max_promedio_m3s": leer(caudal_pron.get(0), "max_promedio_ensamble_m3s"),
        "caudal_pron_1dia_antes_max_promedio_m3s": leer(caudal_pron.get(1), "max_promedio_ensamble_m3s"),
        "pendiente": "; ".join(registro.get("pendiente", [])),
    }


def escribir_tabla() -> int:
    filas = [fila(json.loads(p.read_text(encoding="utf-8"))) for p in CARPETA.rglob("*.json")]
    filas.sort(key=lambda f: (f["fecha"], f["hora"]), reverse=True)
    TABLA.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: Excel reconoce las tildes al abrirlo.
    with TABLA.open("w", newline="", encoding="utf-8-sig") as salida:
        escritor = csv.DictWriter(salida, fieldnames=COLUMNAS, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)
    return len(filas)


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
    args = parser.parse_args()

    eventos: dict[str, dict] = {}
    if args.registros:
        for registro in json.loads(args.registros.read_text(encoding="utf-8")):
            evento = a_evento(registro)
            if evento and args.desde.isoformat() <= evento["fecha"] <= args.hasta.isoformat():
                eventos[evento["id"]] = evento
    else:
        sngr = Sngr()
        for inicio, fin in meses(args.desde, args.hasta):
            for registro in sngr.eventos(inicio, fin):
                evento = a_evento(registro)
                if evento:
                    eventos[evento["id"]] = evento
            print(f"SNGR {inicio:%Y-%m}: {len(eventos)} inundaciones acumuladas", flush=True)

    # Nuevos, o con fuentes pendientes; los ya completos solo actualizan los datos de la SNGR.
    por_procesar, actualizados = [], 0
    for evento in eventos.values():
        archivo = ruta(evento)
        if archivo.exists():
            registro = json.loads(archivo.read_text(encoding="utf-8"))
            ultimo = dt.datetime.fromisoformat(registro.get("procesado", "2000-01-01T00:00:00.000Z").replace("Z", "+00:00"))
            if registro.get("pendiente") and dt.datetime.now(UTC) - ultimo >= REINTENTO_PENDIENTES:
                por_procesar.append(evento)
            elif registro["evento"] != evento:
                registro["evento"] = evento
                archivo.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                actualizados += 1
        else:
            por_procesar.append(evento)
    por_procesar.sort(key=lambda e: e["fecha"], reverse=True)
    tanda = por_procesar[: args.max_eventos]
    print(f"{len(eventos)} inundaciones · {len(por_procesar)} por procesar (esta vez {len(tanda)}) · {actualizados} actualizadas", flush=True)

    persiann = dimension("satellite_based_precipitation", "persiann_pdir_24h", "time")
    persiann = {re.sub(r"\.\d+Z$", ".000Z", v) for v in persiann}
    corridas_wrf = {re.sub(r"\.\d+Z$", ".000Z", v) for v in dimension("wrf", "wrf_precipitation_daily", "INITD")}
    rios = Rios()

    hechos = 0
    with ThreadPoolExecutor(max_workers=args.hilos) as grupo:
        tareas = {grupo.submit(procesar, evento, rios, persiann, corridas_wrf): evento for evento in tanda}
        for tarea in as_completed(tareas):
            evento = tareas[tarea]
            try:
                registro = tarea.result()
            except Exception as error:  # un evento con problemas no detiene el resto
                print(f"  {evento['fecha']} {evento['id'][:8]}: error ({error})", flush=True)
                continue
            archivo = ruta(evento)
            archivo.parent.mkdir(parents=True, exist_ok=True)
            archivo.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            hechos += 1
            if hechos % 50 == 0:
                print(f"  {hechos}/{len(tanda)} procesados", flush=True)

    total = escribir_tabla()
    print(f"Listo: {hechos} eventos procesados · {total} en la tabla eventos/inundaciones.csv"
          + (" (quedan pendientes: vuelve a ejecutar)" if len(por_procesar) > len(tanda) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
