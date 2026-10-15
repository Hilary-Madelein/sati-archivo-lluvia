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
el lugar y el día de cada una, busca la lluvia y el caudal. **Solo se archivan las
que tienen los dos datos**:

| Dato | Fuente | Desde | ¿Obligatorio? |
|---|---|---|---|
| El evento: fecha, hora, provincia, cantón, parroquia, sector, coordenadas, nivel, estado, descripción y afectaciones | SNGR (misma identificación que SATI.EC) | Lo que entregue la API | Sí |
| Lluvia que cayó el día del evento y los 2 anteriores, y el total de los 3 días (en el lugar y la más alta a menos de 5 km) | Satélite PERSIANN (INAMHI) | ene 2025 | **Sí** |
| Caudal del río más cercano ese día y el siguiente, cuántas veces su caudal normal del mes y qué crecida alcanzó (la de 2, 5, 10… años) | GEOGLOWS (simulación diaria) | 1980 (llega hasta ~1 mes atrás) | **Sí** |
| Lluvia que pronosticaba el WRF para ese día (hecho ese día, 1 y 2 días antes) | WRF del INAMHI | nov 2025 | No: se agrega si existe |
| Caudal que pronosticaba GEOGLOWS para ese día (hecho ese día, 1 y 2 días antes) | GEOGLOWS: su API (~2 meses) o su archivo en AWS | ene 2026 | No: se agrega si existe |
| Estación del INAMHI más cercana (a menos de 25 km): **pronóstico puntual** del WRF en la estación para ese día (hecho ese día, 1 y 2 días antes) y la lluvia que midió | Estaciones del INAMHI + WRF | pronóstico: ene 2026 · medición: 13 oct 2026 | No: se agrega si existe |

**El día del evento** es el "día de lluvia" de **07:00 a 07:00** del día siguiente
(hora de Ecuador), igual que el acumulado diario del satélite: un evento de las
19:20 del 11 de octubre usa la lluvia del 11 a las 07:00 al 12 a las 07:00. Uno de
madrugada (antes de las 07:00) cuenta en el día anterior. Cada dato del JSON
indica su periodo con `desde` y `hasta`, y cada bloque trae un `que_es` que lo explica.

Se guarda en `eventos/`:

- **`RESUMEN.md`**: cuántas inundaciones hay completas, pendientes y descartadas,
  y las completas por mes, provincia, lluvia y crecida.
- **`inundaciones.csv`**: una fila por inundación completa, para abrir en Excel.
  La columna `resumen` lo dice en una frase.
- **`inundaciones/AAAA/MM/<id>.json`**: el detalle de cada inundación completa.
- **`pendientes/AAAA/MM/<id>.json`**: esperan un dato que va a llegar (sobre todo
  el caudal: la simulación de GEOGLOWS va ~1 mes atrasada). Se reintentan cada 3
  días y pasan solas a `inundaciones/` cuando se completan.
- **`depurados.csv`**: las inundaciones completas que pasan la **depuración**, con
  las mismas columnas que `inundaciones.csv`. Hoy exige: desde el 1 de enero de
  2026; tipo **desborde de río** o **lluvia intensa (anegamiento)** (se quitan el
  colapso de drenaje y el oleaje o marea); afectación verificada; los tres
  pronósticos completos (WRF en el lugar, caudal y estación del INAMHI cercana);
  lluvia real según el satélite (y, si fue desborde, el río por encima de su
  caudal normal); afectación importante; y uno por cantón y día. El tipo sale de la misma clasificación
  que usa SATI.EC (columna `tipo_inundacion` y bloque `clasificacion` de cada
  JSON), junto con `afectacion_verificada` (si la SNGR registró daño en personas,
  viviendas, cultivos o servicios). Los criterios están al inicio de
  `cruzar_eventos.py` (`DEPURACION_…`) y el RESUMEN muestra cuántas quedan en cada paso.
- **`descartados.csv`**: las que nunca tendrán los dos datos (p. ej. anteriores a
  2025, sin lluvia por satélite), con el motivo.

Los datos de la SNGR de los últimos 30 días se actualizan en cada ejecución
(estado, afectados…).

**Puesta en marcha:** en *Settings → Secrets and variables → Actions → Secrets*, crea
`SNGR_USUARIO` y `SNGR_CLAVE` con el usuario y la clave de la API de la SNGR. Luego
*Actions → "Cruzar inundaciones de la SNGR" → Run workflow* con *desde* = `2025-01-01`
(antes no hay lluvia por satélite, así que esas inundaciones se descartan). Procesa
hasta 1500 eventos por ejecución (unas 2 h); si quedan más, vuelve a ejecutarlo o
deja que lo complete la ejecución diaria.

## Estaciones del INAMHI

La API del INAMHI (`apis.inamhi.gob.ec`) da las estaciones con sus coordenadas y
la lluvia de cada hora, pero **solo de las últimas 12 horas**. `estaciones.py` la
guarda **cada 3 horas** (job "estaciones" del workflow "Cruzar inundaciones de la
SNGR") en `estaciones/`:

| Archivo | Qué tiene |
|---|---|
| `estaciones.csv` | Las 186 estaciones del INAMHI: código, nombre, tipo, coordenadas, altitud, estado y si transmiten (hoy ~74, y ~48 con lluvia) |
| `lluvia_horaria/AAAA-MM.csv` | La lluvia de cada hora en cada estación, en UTC y en hora de Ecuador |
| `lluvia_diaria.csv` | La lluvia de cada día de lluvia (07:00 a 07:00), con cuántas de las 24 horas tienen dato |
| `pronostico_por_estacion.csv` | **Pronóstico puntual de lluvia** en cada una de las 186 estaciones, **día por día desde el 1 de enero de 2026**: lo que pronosticaba el WRF en las coordenadas de la estación para cada día del WRF (02:00 a 02:00), hecho el mismo día, 1 y 2 días antes. Desde que se archiva cada estación, también la lluvia que midió en esas mismas 24 h, para comparar |

El cruce de inundaciones agrega, si hay, la **estación más cercana a menos de
25 km** con la lluvia que midió el día del evento (`lluvia_estacion_inamhi`).
La lluvia medida solo existe desde que empezó este archivo (13 oct 2026): la API
no da fechas anteriores. El pronóstico, en cambio, se saca del historial de
corridas del WRF, por eso cubre todo 2026. La primera ejecución lo calcula
completo (~15 min); después solo agrega el día nuevo.

Avisos sobre la API: las horas vienen marcadas "-05:00" pero son UTC (a las 08:55
de Ecuador ya trae el dato "13:00"); cada valor se toma como la lluvia de la hora
que termina en esa hora.

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
