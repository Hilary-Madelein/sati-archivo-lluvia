# Precisión del pronóstico de lluvia (WRF) en las inundaciones de la SNGR

Se rehace en cada cruce de eventos (`precision_pronostico.py`). Tabla por evento:
`precision_pronostico.csv` (todas) y `precision_pronostico_depurados.csv` (selección depurada).

- **Observado:** lluvia del satélite PERSIANN el día del evento (07:00 a 07:00, hora de Ecuador), en el lugar.
  Cuando hay una estación del INAMHI a menos de 25 km, la columna `observado_estacion_mm` trae lo que midió.
- **Pronosticado:** lluvia diaria del WRF (visor oficial del INAMHI) hecha el mismo día, en el lugar. Su día va
  de 02:00 a 02:00, 5 h antes que el del satélite.
- **Sesgo:** pronosticado − observado, en promedio (positivo = el pronóstico se pasa; negativo = se queda corto).
- **Categoría:** la de lluvia en 24 h del documento de la SNGR (Mínima, Ligera, Moderada, Fuerte, Intensa,
  Torrencial, Extrema). **Alerta moderada o más:** el pronóstico llegaba a 10 mm o más (lo que dispararía una alerta).

## Resumen

| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Pronosticado / observado | Acierta categoría | Pronóstico de alerta moderada o más |
|---|---|---|---|---|---|---|---|---|
| Todas las inundaciones | 1933 | 34.0 | 19.6 | -14.4 | 29.1 | 0.58 | 27 % | 46 % |
| Selección depurada | 42 | 61.0 | 23.8 | -37.2 | 48.3 | 0.39 | 5 % | 45 % |

## Por región

| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Pronosticado / observado | Acierta categoría | Pronóstico de alerta moderada o más |
|---|---|---|---|---|---|---|---|---|
| Costa | 1460 | 36.5 | 18.9 | -17.6 | 30.5 | 0.52 | 26 % | 45 % |
| Sierra | 348 | 25.3 | 25.4 | +0.1 | 23.8 | 1.01 | 30 % | 57 % |
| Amazonía | 125 | 28.7 | 11.3 | -17.5 | 26.6 | 0.39 | 28 % | 33 % |
| Insular | 0 | | | | | | | |

## Por nivel de impacto de la SNGR

| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Pronosticado / observado | Acierta categoría | Pronóstico de alerta moderada o más |
|---|---|---|---|---|---|---|---|---|
| Nivel 1 | 1700 | 33.8 | 19.6 | -14.2 | 28.5 | 0.58 | 27 % | 47 % |
| Nivel 2 | 209 | 34.8 | 19.0 | -15.8 | 32.8 | 0.54 | 25 % | 43 % |
| Nivel 3 | 23 | 39.5 | 18.9 | -20.6 | 34.3 | 0.48 | 35 % | 35 % |
| Nivel 4 | 1 | 0.0 | 38.3 | +38.3 | 38.3 |  | 0 % | 100 % |

## Por categoría del evento

| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Pronosticado / observado | Acierta categoría | Pronóstico de alerta moderada o más |
|---|---|---|---|---|---|---|---|---|
| Colapso de drenaje | 238 | 28.7 | 21.2 | -7.5 | 26.7 | 0.74 | 26 % | 49 % |
| Desborde de río | 574 | 37.9 | 22.0 | -15.9 | 31.9 | 0.58 | 25 % | 49 % |
| Lluvia intensa (anegamiento) | 1118 | 33.1 | 18.0 | -15.0 | 28.1 | 0.55 | 28 % | 45 % |
| Oleaje o marea | 3 | 40.0 | 0.7 | -39.3 | 39.3 | 0.02 | 33 % | 0 % |
