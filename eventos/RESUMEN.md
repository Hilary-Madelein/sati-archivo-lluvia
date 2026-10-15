# Inundaciones de la SNGR cruzadas con lluvia y caudal

Actualizado el 2026-10-15. Se genera solo en cada cruce; ver el README para qué tiene cada archivo.

| Inundaciones | Cantidad |
|---|---:|
| **Completas**: con lluvia por satélite y caudal del río (`inundaciones/`, `inundaciones.csv`) | **1429** |
| …de ellas, con el pronóstico de lluvia del WRF para ese día | 1374 |
| …de ellas, con el pronóstico de caudal de GEOGLOWS para ese día | 1362 |
| …de ellas, con el pronóstico puntual del WRF en una estación del INAMHI a menos de 25 km | 1193 |
| …de ellas, con la lluvia medida en esa estación (hay mediciones desde oct 2026) | 0 |
| Pendientes: esperan un dato que llegará (`pendientes/`) | 118 |
| Descartadas: nunca tendrán los dos datos (`descartados.csv`) | 0 |

## Depuración (`depurados.csv`)

Cada paso deja solo las inundaciones que cumplen el criterio (se ajusta en `cruzar_eventos.py`, DEPURACION_…).

| Paso | Quedan |
|---|---:|
| Completas (lluvia por satélite y caudal del río) | 1429 |
| …desde el 2026-01-01 | 1362 |
| …de tipo desborde de río o lluvia intensa (anegamiento) (se quitan colapso de drenaje y oleaje o marea) | 1194 |
| …con afectación verificada por la SNGR (daño en personas, viviendas, cultivos o servicios) | 751 |
| …con el pronóstico WRF en el lugar de las 3 corridas (mismo día, 1 y 2 días antes) | 716 |
| …con el pronóstico de caudal de las 3 corridas | 712 |
| …con pronóstico puntual en una estación del INAMHI a menos de 25 km | 598 |
| …con lluvia real: satélite ≥ 20 mm ese día o ≥ 50 mm en 3 días; si fue desborde, el río ≥ 2 veces su caudal normal | 340 |
| …con afectación importante: ≥ 10 personas, ≥ 5 viviendas, evacuados o damnificados, o Nivel 2+ | 224 |
| **…uno por cantón y día (el de más personas afectadas)** | **183** |

| Tipo de inundación (depuradas) | Inundaciones |
|---|---:|
| Lluvia intensa (anegamiento) | 109 |
| Desborde de río | 74 |

## Completas, según la crecida que alcanzó el río

| Crecida (caudal simulado) | Inundaciones |
|---|---:|
| Ninguna (no llegó a la de 2 años) | 1345 |
| Superó la de 2 años | 68 |
| Superó la de 5 años | 12 |
| Superó la de 10 años | 4 |

## Completas, según la lluvia del día del evento

La más alta a menos de 5 km medida por el satélite.

| Lluvia | Inundaciones |
|---|---:|
| Menos de 5 mm | 274 |
| 5 a 20 mm | 461 |
| 20 a 50 mm | 379 |
| 50 mm o más | 315 |

## Completas, por mes

| Mes | Inundaciones |
|---|---:|
| 2026-09 | 95 |
| 2026-08 | 7 |
| 2026-07 | 18 |
| 2026-06 | 79 |
| 2026-05 | 67 |
| 2026-04 | 90 |
| 2026-03 | 476 |
| 2026-02 | 428 |
| 2026-01 | 102 |
| 2025-12 | 5 |
| 2025-11 | 33 |
| 2025-10 | 29 |

## Completas, por provincia

| Provincia | Inundaciones |
|---|---:|
| Guayas | 538 |
| El Oro | 133 |
| Pichincha | 121 |
| Los Ríos | 113 |
| Esmeraldas | 84 |
| Manabí | 77 |
| Azuay | 68 |
| Santo Domingo De Los Tsáchilas | 35 |
| Orellana | 35 |
| Santa Elena | 30 |
| Loja | 28 |
| Pastaza | 24 |
| Zamora Chinchipe | 20 |
| Napo | 18 |
| Morona Santiago | 17 |
| Bolívar | 16 |
| Cotopaxi | 15 |
| Tungurahua | 12 |
| Carchi | 12 |
| Imbabura | 10 |
| Chimborazo | 9 |
| Sucumbíos | 7 |
| Cañar | 6 |
| Galápagos | 1 |
