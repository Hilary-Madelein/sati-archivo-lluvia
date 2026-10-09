#!/usr/bin/env python3
"""
Archiva la lluvia del INAMHI antes de que el servidor la borre.

- Pronóstico WRF: cada corrida completa, en pasos de 3 h y en días de 24 h.
- Lluvia observada por satélite PERSIANN: el acumulado de 24 h de cada día.

Los datos salen del GeoServer del INAMHI alojado por GEOGLOWS (el mismo que usa
SATI.EC) como GeoTIFF comprimidos, y se publican en las Releases de este
repositorio (una release por mes y producto). `catalogo.json` lleva la cuenta
de lo archivado: lo que ya está no se vuelve a descargar.

Solo usa la biblioteca estándar de Python y la herramienta `gh` de GitHub.

Uso:
    python archivar.py                          # últimos 7 días (lo que hace el workflow a diario)
    python archivar.py --desde 2025-11-25       # todo lo que el servidor tenga desde esa fecha
    python archivar.py --desde 2026-10-01 --hasta 2026-10-03 --sin-subir   # prueba local, sin GitHub
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

SERVIDOR = "https://services.geoglows.org/geoserver"
WRF_3H = ("wrf", "wrf_precipitation")
WRF_DIARIO = ("wrf", "wrf_precipitation_daily")
PERSIANN_24H = ("satellite_based_precipitation", "persiann_pdir_24h")
# Ecuador continental [oeste, sur, este, norte]; el WRF ya viene recortado al país.
BBOX_ECUADOR = (-81.2, -5.1, -75.1, 1.6)

# Pasos que se prueban por corrida: el WRF llega hasta +72 h (cada 3 h y por día).
PASOS_3H = 29  # 0 … +84 h
PASOS_DIARIOS = 4  # 0 … +72 h

RAIZ = Path(__file__).resolve().parent
CATALOGO = RAIZ / "catalogo.json"
SALIDA = RAIZ / "salida"


# ── Descargas ───────────────────────────────────────────────────────────


def descargar(url: str, intentos: int = 3, espera: float = 10.0) -> tuple[int, bytes]:
    """GET con reintentos ante errores de red o 5xx. Devuelve (estado, cuerpo)."""
    for intento in range(1, intentos + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as respuesta:
                return respuesta.status, respuesta.read()
        except urllib.error.HTTPError as error:
            if error.code < 500 or intento == intentos:
                return error.code, b""
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if intento == intentos:
                raise
        time.sleep(espera * intento)
    raise RuntimeError("inalcanzable")


def es_geotiff(cuerpo: bytes) -> bool:
    return cuerpo[:4] in (b"II*\x00", b"MM\x00*")


def iso(momento: dt.datetime) -> str:
    return momento.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def url_cobertura(espacio: str, capa: str, subconjuntos: list[str]) -> str:
    """WCS 2.0 GetCoverage en GeoTIFF comprimido (DEFLATE). Las comillas van codificadas (%22)."""
    parametros = [
        ("service", "WCS"),
        ("version", "2.0.1"),
        ("request", "GetCoverage"),
        ("format", "image/tiff"),
        ("geotiff:compression", "DEFLATE"),
        ("geotiff:predictor", "FloatingPoint"),
        ("coverageId", f"{espacio}__{capa}"),
    ] + [("subset", subconjunto) for subconjunto in subconjuntos]
    return f"{SERVIDOR}/{espacio}/wcs?" + urllib.parse.urlencode(parametros, safe="(),:")


def dimensiones(espacio: str, capa: str) -> dict[str, list[dt.datetime]]:
    """Valores de las dimensiones (time, INITD) de una capa, según el GetCapabilities del WMS."""
    estado, cuerpo = descargar(f"{SERVIDOR}/{espacio}/wms?service=WMS&version=1.3.0&request=GetCapabilities")
    if estado != 200:
        raise RuntimeError(f"GetCapabilities de {espacio} respondió HTTP {estado}")
    xml = cuerpo.decode("utf-8", errors="replace")
    bloque = re.search(rf"<Name>{re.escape(capa)}</Name>(.*?)</Layer>", xml, re.S)
    if not bloque:
        raise RuntimeError(f"La capa {capa} no está en el servidor")
    resultado: dict[str, list[dt.datetime]] = {}
    for nombre, valores in re.findall(r'<Dimension name="(\w+)"[^>]*>([^<]*)</Dimension>', bloque.group(1)):
        resultado[nombre] = sorted(
            dt.datetime.fromisoformat(valor.strip().replace("Z", "+00:00")) for valor in valores.split(",") if valor.strip()
        )
    return resultado


# ── Productos ───────────────────────────────────────────────────────────


def archivar_wrf(fecha: dt.date, inicio_3h: dt.datetime | None, inicio_diario: dt.datetime | None) -> Path | None:
    """Una corrida del WRF en un .zip: pasos de 3 h, días de 24 h e info.json."""
    destino = SALIDA / f"wrf_{fecha:%Y%m%d}.zip"
    pasos: list[str] = []
    dias: list[str] = []
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_STORED) as archivo:
        if inicio_3h:
            for k in range(PASOS_3H):
                momento = inicio_3h + dt.timedelta(hours=3 * k)
                estado, cuerpo = descargar(url_cobertura(*WRF_3H, [f'INITD("{iso(inicio_3h)}")', f'time("{iso(momento)}")']))
                if estado == 200 and es_geotiff(cuerpo):
                    archivo.writestr(f"3h/wrf_3h_{momento:%Y%m%dT%H%M}Z.tif", cuerpo)
                    pasos.append(iso(momento))
        if inicio_diario:
            for k in range(PASOS_DIARIOS):
                momento = inicio_diario + dt.timedelta(days=k)
                estado, cuerpo = descargar(url_cobertura(*WRF_DIARIO, [f'INITD("{iso(inicio_diario)}")', f'time("{iso(momento)}")']))
                if estado == 200 and es_geotiff(cuerpo):
                    archivo.writestr(f"diario/wrf_24h_desde_{momento:%Y%m%dT%H%M}Z.tif", cuerpo)
                    dias.append(iso(momento))
        if not pasos and not dias:
            archivo.close()
            destino.unlink()
            return None
        archivo.writestr(
            "info.json",
            json.dumps(
                {
                    "producto": "Pronóstico de lluvia del modelo WRF del INAMHI",
                    "unidad": "mm",
                    "corrida_3h": iso(inicio_3h) if inicio_3h else None,
                    "corrida_diaria": iso(inicio_diario) if inicio_diario else None,
                    "pasos_3h": pasos,
                    "dias_24h": dias,
                    "nota": "Horas en UTC (Ecuador = UTC-5), tal como las publica el servidor. Cada diario acumula las 24 h que EMPIEZAN a su hora (la suma de los pasos de 3 h siguientes coincide con él, salvo un factor x2 que hay que confirmar con el INAMHI).",
                    "fuente": f"{SERVIDOR}/wrf (WCS)",
                    "descargado": iso(dt.datetime.now(dt.timezone.utc)),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    return destino


def archivar_persiann(dia: dt.datetime) -> Path | None:
    """Lluvia observada de 24 h de un día (GeoTIFF, recortado a Ecuador)."""
    oeste, sur, este, norte = BBOX_ECUADOR
    estado, cuerpo = descargar(
        url_cobertura(*PERSIANN_24H, [f'time("{iso(dia)}")', f"Lat({sur},{norte})", f"Long({oeste},{este})"])
    )
    if estado != 200 or not es_geotiff(cuerpo):
        return None
    destino = SALIDA / f"persiann_24h_{dia:%Y%m%d}.tif"
    destino.write_bytes(cuerpo)
    return destino


# ── GitHub Releases y catálogo ──────────────────────────────────────────


def gh(*argumentos: str, verificar: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *argumentos], check=verificar, capture_output=True, text=True)


def publicar(etiqueta: str, titulo: str, nota: str, archivo: Path) -> str:
    """Sube el archivo a la release del mes (la crea si no existe). Devuelve la URL de descarga."""
    if gh("release", "view", etiqueta, verificar=False).returncode != 0:
        gh("release", "create", etiqueta, "--title", titulo, "--notes", nota)
    gh("release", "upload", etiqueta, str(archivo), "--clobber")
    repositorio = os.environ.get("GITHUB_REPOSITORY", "")
    return f"https://github.com/{repositorio}/releases/download/{etiqueta}/{archivo.name}"


def cargar_catalogo() -> dict:
    if CATALOGO.exists():
        return json.loads(CATALOGO.read_text(encoding="utf-8"))
    return {"wrf": {}, "persiann_24h": {}}


def guardar_catalogo(catalogo: dict) -> None:
    catalogo["actualizado"] = iso(dt.datetime.now(dt.timezone.utc))
    for clave in ("wrf", "persiann_24h"):
        catalogo[clave] = dict(sorted(catalogo.get(clave, {}).items()))
    CATALOGO.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ── Programa ────────────────────────────────────────────────────────────


def main() -> int:
    hoy = dt.datetime.now(dt.timezone.utc).date()
    parser = argparse.ArgumentParser(description="Archiva la lluvia del INAMHI (WRF y PERSIANN) en GitHub Releases.")
    parser.add_argument("--desde", type=dt.date.fromisoformat, default=hoy - dt.timedelta(days=7))
    parser.add_argument("--hasta", type=dt.date.fromisoformat, default=hoy)
    parser.add_argument("--max-archivos", type=int, default=1000, help="tope de archivos nuevos por ejecución")
    parser.add_argument("--solo", choices=["wrf", "persiann"], help="archivar un solo producto")
    parser.add_argument("--sin-subir", action="store_true", help="prueba local: deja los archivos en ./salida")
    args = parser.parse_args()

    SALIDA.mkdir(exist_ok=True)
    catalogo = cargar_catalogo()
    nuevos = 0
    print(f"Archivando del {args.desde} al {args.hasta}")

    if args.solo in (None, "wrf"):
        corridas_3h = {momento.date(): momento for momento in dimensiones(*WRF_3H).get("INITD", [])}
        corridas_diarias = {momento.date(): momento for momento in dimensiones(*WRF_DIARIO).get("INITD", [])}
        fechas = sorted(f for f in set(corridas_3h) | set(corridas_diarias) if args.desde <= f <= args.hasta)
        print(f"WRF: {len(fechas)} corridas en el rango; {sum(f.strftime('%Y%m%d') in catalogo['wrf'] for f in fechas)} ya archivadas")
        for fecha in fechas:
            clave = fecha.strftime("%Y%m%d")
            if clave in catalogo["wrf"] or nuevos >= args.max_archivos:
                continue
            archivo = archivar_wrf(fecha, corridas_3h.get(fecha), corridas_diarias.get(fecha))
            if not archivo:
                print(f"  {clave}: el servidor no tiene datos de esa corrida")
                continue
            with zipfile.ZipFile(archivo) as contenido:
                info = json.loads(contenido.read("info.json"))
            etiqueta = f"wrf-{fecha:%Y-%m}"
            url = None if args.sin_subir else publicar(
                etiqueta, f"WRF INAMHI · {fecha:%Y-%m}", "Corridas del pronóstico de lluvia WRF del INAMHI (GeoTIFF, mm). Ver catalogo.json.", archivo
            )
            catalogo["wrf"][clave] = {
                "release": etiqueta,
                "archivo": archivo.name,
                "pasos_3h": len(info["pasos_3h"]),
                "dias_24h": len(info["dias_24h"]),
                "bytes": archivo.stat().st_size,
                "url": url,
            }
            nuevos += 1
            print(f"  {clave}: {len(info['pasos_3h'])} pasos de 3 h, {len(info['dias_24h'])} días · {archivo.stat().st_size / 1e6:.1f} MB")
            if not args.sin_subir:
                archivo.unlink()
                guardar_catalogo(catalogo)

    if args.solo in (None, "persiann"):
        dias = [momento for momento in dimensiones(*PERSIANN_24H).get("time", []) if args.desde <= momento.date() <= args.hasta]
        print(f"PERSIANN: {len(dias)} días en el rango")
        for dia in dias:
            clave = dia.strftime("%Y%m%d")
            if clave in catalogo["persiann_24h"] or nuevos >= args.max_archivos:
                continue
            archivo = archivar_persiann(dia)
            if not archivo:
                print(f"  {clave}: sin dato en el servidor")
                continue
            etiqueta = f"persiann-{dia:%Y-%m}"
            url = None if args.sin_subir else publicar(
                etiqueta, f"PERSIANN 24 h · {dia:%Y-%m}", "Lluvia observada por satélite PERSIANN, acumulado de 24 h por día (GeoTIFF, mm).", archivo
            )
            catalogo["persiann_24h"][clave] = {"release": etiqueta, "archivo": archivo.name, "bytes": archivo.stat().st_size, "url": url}
            nuevos += 1
            if not args.sin_subir:
                archivo.unlink()
                guardar_catalogo(catalogo)
        print(f"  {sum(d.strftime('%Y%m%d') in catalogo['persiann_24h'] for d in dias)} de {len(dias)} días archivados")

    if not args.sin_subir:
        guardar_catalogo(catalogo)
    print(f"Listo: {nuevos} archivos nuevos." + (" (Quedaron pendientes: vuelve a ejecutar.)" if nuevos >= args.max_archivos else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
