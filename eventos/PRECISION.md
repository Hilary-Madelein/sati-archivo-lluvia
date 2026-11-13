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
| Todas las inundaciones | 2028 | 33.6 | 19.8 | -13.8 | 29.2 | 26 % | 47 % |
| Selección depurada | 43 | 61.9 | 24.3 | -37.6 | 48.5 | 5 % | 49 % |

## Por región

| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Acierta categoría | Pronóstico de alerta moderada o más |
|---|---|---|---|---|---|---|---|
| Costa | 1549 | 35.8 | 19.2 | -16.6 | 30.5 | 26 % | 45 % |
| Sierra | 353 | 25.6 | 25.4 | -0.3 | 24.2 | 29 % | 57 % |
| Amazonía | 126 | 28.8 | 11.2 | -17.6 | 26.7 | 28 % | 33 % |
| Insular | 0 | | | | | | |

## Por nivel de impacto de la SNGR

| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Acierta categoría | Pronóstico de alerta moderada o más |
|---|---|---|---|---|---|---|---|
| Nivel 1 | 1787 | 33.3 | 19.9 | -13.4 | 28.6 | 27 % | 47 % |
| Nivel 2 | 216 | 35.1 | 18.4 | -16.7 | 33.0 | 25 % | 42 % |
| Nivel 3 | 24 | 43.8 | 19.5 | -24.2 | 37.4 | 33 % | 38 % |
| Nivel 4 | 1 | 0.0 | 38.3 | +38.3 | 38.3 | 0 % | 100 % |

## Por categoría del evento

| Grupo | Eventos | Observado prom. (mm) | Pronosticado prom. (mm) | Sesgo (mm) | Error absoluto prom. (mm) | Acierta categoría | Pronóstico de alerta moderada o más |
|---|---|---|---|---|---|---|---|
| Colapso de drenaje | 241 | 28.5 | 21.4 | -7.1 | 26.5 | 26 % | 49 % |
| Desborde de río | 603 | 37.4 | 21.8 | -15.6 | 32.1 | 25 % | 48 % |
| Lluvia intensa (anegamiento) | 1181 | 32.7 | 18.5 | -14.2 | 28.2 | 27 % | 45 % |
| Oleaje o marea | 3 | 40.0 | 0.7 | -39.3 | 39.3 | 33 % | 0 % |
