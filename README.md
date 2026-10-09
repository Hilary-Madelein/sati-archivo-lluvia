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
