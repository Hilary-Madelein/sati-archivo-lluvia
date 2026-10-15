# Inundaciones de la SNGR cruzadas con lluvia y caudal

Actualizado el 2026-10-15; se rehace solo en cada cruce. Qué es cada dato: [`GUIA.md`](GUIA.md).

## Selección depurada: **94 inundaciones** (`depurados.csv`)

Cada paso deja solo las que cumplen el criterio. Los umbrales están al inicio de `cruzar_eventos.py` (`DEPURACION_…`): para afinar la selección se cambia un número y el siguiente cruce rehace esta tabla.

| Paso | Quedan |
|---|---:|
| Completas (lluvia por satélite y caudal del río) | 1429 |
| …desde el 2026-01-01 | 1362 |
| …de tipo desborde de río o lluvia intensa (anegamiento) (se quitan colapso de drenaje y oleaje o marea) | 1194 |
| …con afectación verificada por la SNGR (daño en personas, viviendas, cultivos o servicios) | 751 |
| …con el pronóstico WRF en el lugar de las 3 corridas (mismo día, 1 y 2 días antes) | 716 |
| …con el pronóstico de caudal de las 3 corridas | 712 |
| …con pronóstico puntual en una estación del INAMHI a ≤ 15 km | 407 |
| …con lluvia real: el satélite midió ≥ 30 mm ese día o ≥ 75 mm en 3 días | 222 |
| …si fue desborde: el río llevaba ≥ 3 veces su caudal normal y no es un arroyo (caudal normal ≥ 1 m³/s) | 168 |
| …con afectación importante: ≥ 10 personas, ≥ 5 viviendas, evacuados o damnificados, o Nivel 2+ | 106 |
| **…uno por cantón y día (el de más personas afectadas)** | **94** |

### Por tipo de inundación

| Tipo | Inundaciones |
|---|---:|
| Lluvia intensa (anegamiento) | 66 |
| Desborde de río | 28 |

### Por lluvia del día del evento

La más alta a menos de 5 km medida por el satélite.

| Lluvia | Inundaciones |
|---|---:|
| Menos de 30 mm | 29 |
| 30 a 50 mm | 21 |
| 50 a 100 mm | 30 |
| 100 mm o más | 14 |

### Desbordes, según la crecida que alcanzó el río (GEOGLOWS)

| Crecida | Desbordes |
|---|---:|
| Ninguna (no llegó a la de 2 años) | 22 |
| Superó la de 2 años | 5 |
| Superó la de 10 años | 1 |

### Por mes

| Mes | Inundaciones |
|---|---:|
| 2026-09 | 2 |
| 2026-07 | 4 |
| 2026-06 | 3 |
| 2026-05 | 1 |
| 2026-04 | 1 |
| 2026-03 | 45 |
| 2026-02 | 37 |
| 2026-01 | 1 |

### Por provincia

| Provincia | Inundaciones |
|---|---:|
| Guayas | 45 |
| Los Ríos | 15 |
| Manabí | 10 |
| El Oro | 7 |
| Esmeraldas | 5 |
| Santa Elena | 3 |
| Loja | 2 |
| Chimborazo | 2 |
| Pastaza | 1 |
| Cotopaxi | 1 |
| Orellana | 1 |
| Cañar | 1 |
| Napo | 1 |

## Archivo completo (todas las inundaciones cruzadas)

| Inundaciones | Cantidad |
|---|---:|
| Completas: con lluvia por satélite y caudal del río (`inundaciones/`, `inundaciones.csv`) | 1429 |
| …con el pronóstico de lluvia del WRF para ese día | 1374 |
| …con el pronóstico de caudal de GEOGLOWS para ese día | 1362 |
| …con pronóstico puntual en una estación del INAMHI a menos de 25 km | 1193 |
| …con la lluvia medida en esa estación (hay mediciones desde oct 2026) | 0 |
| Pendientes: esperan un dato que llegará (`pendientes/`) | 118 |
| Descartadas: nunca tendrán los dos datos (`descartados.csv`) | 0 |
