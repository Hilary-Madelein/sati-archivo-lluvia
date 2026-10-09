# SATI.EC · Archivo de lluvia del INAMHI

Copia propia de la lluvia que publica el INAMHI, para que no se pierda cuando su
servidor borre lo antiguo. Un workflow de GitHub Actions la descarga **cada día**
y la publica en las **Releases** de este repositorio.

| Producto | Qué es | Desde | Tamaño |
|---|---|---|---|
| **Pronóstico WRF** | Cada corrida diaria completa: lluvia cada 3 h (+72 h) y por día | 25 nov 2025 (lo que el servidor conserva) | ~2,3 MB por corrida · ~850 MB por año |
| **Satélite PERSIANN 24 h** | Lluvia observada: acumulado de 24 h de cada día | 1 ene 2025 | ~10 KB por día · ~4 MB por año |

Fuente: GeoServer del INAMHI alojado por GEOGLOWS (`https://services.geoglows.org/geoserver`, el que usa el visor oficial inamhi.geoglows.org),
el mismo que usa SATI.EC. Todo en **GeoTIFF comprimido, en mm**, recortado al
Ecuador continental; se abre directo en QGIS, Python (rasterio) o R.

## Inundaciones de la SNGR cruzadas con lluvia y caudal

Cada día, `cruzar_eventos.py` toma las **inundaciones** que registra la SNGR y, para
el punto y el día de cada una, guarda:

| Dato | Fuente | Desde |
|---|---|---|
| El evento: fecha, hora, provincia, cantón, parroquia, sector, coordenadas, nivel, estado, descripción y afectaciones | SNGR (misma identificación que SATI.EC) | Lo que entregue la API (hay datos desde 2018) |
| Lluvia observada el día del evento y los 2 anteriores, y el acumulado de 72 h (en el punto y la máxima en ~5 km) | Satélite PERSIANN (INAMHI) | ene 2025 |
| Lluvia pronosticada para ese día por las corridas del mismo día, de 1 y de 2 días antes | WRF del INAMHI | nov 2025 |
| Río más cercano: caudal simulado ese día, periodos de retorno de 2 a 100 años y cuál superó | GEOGLOWS (simulación histórica) | 1980 (llega hasta ~1 mes atrás) |
| Lo que se pronosticaba para el caudal de ese día (corridas del mismo día, de 1 y 2 días antes) | GEOGLOWS | últimos ~2 meses |

Se guarda en `eventos/`:

- **`eventos/inundaciones.csv`**: una fila por evento, para abrir en Excel.
- **`eventos/inundaciones/AAAA/MM/<id>.json`**: el detalle completo de cada evento.

Si una fuente aún no tiene datos para un evento reciente (la simulación del río va
~1 mes atrasada), queda en la columna `pendiente` y se completa sola en un archivado
posterior (se reintenta cada 3 días). Los datos de la SNGR de los últimos 30 días se
actualizan en cada ejecución (estado, afectados…).

**Puesta en marcha:** en *Settings → Secrets and variables → Actions → Secrets*, crea
`SNGR_USUARIO` y `SNGR_CLAVE` con el usuario y la clave de la API de la SNGR. Luego
*Actions → "Cruzar inundaciones de la SNGR" → Run workflow* con *desde* = `2018-01-01`
para el histórico. Procesa hasta 1500 eventos por ejecución (unas 2 h); si quedan
más, vuelve a ejecutarlo o deja que lo complete la ejecución diaria.

## Dónde están los archivos

- **Releases** del repositorio, una por mes y producto: `wrf-2026-10`, `persiann-2026-10`…
- **`catalogo.json`**: índice de todo lo archivado, con el enlace de descarga de cada archivo.

Cada corrida del WRF es un `.zip` (`wrf_20261008.zip`) con:

```
3h/wrf_3h_20261008T0100Z.tif          ← un archivo por paso de 3 h (25 por corrida)
diario/wrf_24h_desde_20261008T0700Z.tif ← un archivo por día (2–3 por corrida)
info.json                             ← corrida, pasos, unidades y fuente
```

Las horas están en **UTC** (Ecuador = UTC−5). Cada archivo diario acumula las
24 h que **empiezan** a su hora: la suma de los pasos de 3 h siguientes coincide
con él, salvo un factor ×2 entre los dos productos que hay que confirmar con el
INAMHI.

## Puesta en marcha (una sola vez)

1. Crea en GitHub un repositorio **público** vacío (p. ej. `sati-archivo-lluvia`)
   y sube esta carpeta.
2. En el repositorio: **Settings → Actions → General → Workflow permissions** →
   marca **"Read and write permissions"** y guarda (el workflow necesita crear
   Releases y guardar `catalogo.json`).
3. **Bajar el histórico**: pestaña **Actions → "Archivar lluvia del INAMHI" →
   Run workflow**, con *desde* = `2025-01-01`. Tarda unas 3 horas (300 corridas
   del WRF y 650 días de PERSIANN). Si se corta, vuelve a ejecutarlo: sigue
   donde quedó.
4. Desde ahí corre solo **dos veces al día** (08:15 y 18:15 de Ecuador) y guarda
   lo nuevo.

## Probar en local

```bash
python3 archivar.py --desde 2026-10-07 --hasta 2026-10-08 --sin-subir   # deja los archivos en ./salida
```

Sin `--sin-subir` necesita la herramienta `gh` con sesión iniciada.

## Avisos

- GitHub pausa los workflows programados si el repositorio pasa 60 días sin
  cambios. Este hace un commit de `catalogo.json` cada vez que archiva algo, así
  que se mantiene activo solo.
- Si el INAMHI cambia el servidor o los nombres de las capas, el workflow
  fallará (GitHub avisa por correo) y habrá que ajustar `archivar.py`.
