# Precisión del pronóstico de lluvia (WRF) en las inundaciones de la SNGR

Se rehace en cada cruce de eventos (`precision_pronostico.py`). Tabla por evento:
`precision_pronostico.csv` (todas) y `precision_pronostico_depurados.csv` (selección depurada).

- **Observado:** lluvia del satélite PERSIANN el día del evento (07:00 a 07:00, hora de Ecuador), en el lugar.
- **Pronosticado:** lluvia diaria del WRF (visor oficial del INAMHI) hecha el mismo día, en el lugar. Su día va
  de 02:00 a 02:00, 5 h antes que el del satélite.
- **Diferencia** (`diferencia_pronostico_menos_observado_mm`): pronóstico del mismo día − observado. **Sesgo:** su promedio
  (positivo = el pronóstico se pasa; negativo = se queda corto).
- **Categoría:** la de lluvia en 24 h del documento de la SNGR (Mínima, Ligera, Moderada, Fuerte, Intensa,
  Torrencial, Extrema). **Alerta moderada o más:** el pronóstico llegaba a 10 mm o más (lo que dispararía una alerta).

## Resumen

| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Acierta categoría | Pronóstico de alerta moderada o más |
|---|---|---|---|---|---|---|---|
| Todas las inundaciones | 1963 | 33.9 | 19.6 | -14.3 | 29.2 | 27 % | 46 % |
| Selección depurada | 42 | 61.0 | 23.8 | -37.2 | 48.3 | 5 % | 45 % |

## Por región

| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Acierta categoría | Pronóstico de alerta moderada o más |
|---|---|---|---|---|---|---|---|
| Costa | 1487 | 36.3 | 19.0 | -17.3 | 30.6 | 26 % | 45 % |
| Sierra | 350 | 25.7 | 25.3 | -0.3 | 24.2 | 30 % | 57 % |
| Amazonía | 126 | 28.8 | 11.2 | -17.6 | 26.7 | 28 % | 33 % |
| Insular | 0 | | | | | | |

## Por nivel de impacto de la SNGR

| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Acierta categoría | Pronóstico de alerta moderada o más |
|---|---|---|---|---|---|---|---|
| Nivel 1 | 1724 | 33.7 | 19.7 | -14.0 | 28.6 | 27 % | 47 % |
| Nivel 2 | 215 | 34.9 | 18.5 | -16.4 | 32.9 | 25 % | 42 % |
| Nivel 3 | 23 | 39.5 | 18.9 | -20.6 | 34.3 | 35 % | 35 % |
| Nivel 4 | 1 | 0.0 | 38.3 | +38.3 | 38.3 | 0 % | 100 % |

## Por categoría del evento

| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Acierta categoría | Pronóstico de alerta moderada o más |
|---|---|---|---|---|---|---|---|
| Colapso de drenaje | 238 | 28.5 | 21.3 | -7.2 | 26.4 | 26 % | 49 % |
| Desborde de río | 584 | 38.1 | 22.1 | -16.0 | 32.3 | 25 % | 49 % |
| Lluvia intensa (anegamiento) | 1138 | 32.9 | 18.0 | -14.9 | 28.1 | 27 % | 45 % |
| Oleaje o marea | 3 | 40.0 | 0.7 | -39.3 | 39.3 | 33 % | 0 % |
