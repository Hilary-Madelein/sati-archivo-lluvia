# Inundaciones de la SNGR cruzadas con lluvia y caudal

Actualizado el 2026-10-29; se rehace solo en cada cruce. Qué es cada dato: [`GUIA.md`](GUIA.md).

## Selección depurada: **32 inundaciones** (`depurados.csv`)

Cada paso deja solo las que cumplen el criterio. Los umbrales están al inicio de `cruzar_eventos.py` (`DEPURACION_…`): para afinar la selección se cambia un número y el siguiente cruce rehace esta tabla.

| Paso | Quedan |
|---|---:|
| Completas (lluvia por satélite y caudal del río) | 1620 |
| …desde el 2026-01-01 | 1553 |
| …de tipo desborde de río o lluvia intensa (anegamiento) (se quitan colapso de drenaje y oleaje o marea) | 1354 |
| …con afectación verificada por la SNGR (daño en personas, viviendas, cultivos o servicios) | 853 |
| …con el pronóstico WRF en el lugar de las 3 corridas (mismo día, 1 y 2 días antes) | 786 |
| …con el pronóstico de caudal de las 3 corridas | 781 |
| …con pronóstico puntual en una estación del INAMHI a ≤ 15 km | 439 |
| …con lluvia real el mismo día: el satélite midió ≥ 30 mm | 159 |
| …si fue desborde: el río llevaba ≥ 3 veces su caudal normal y no es un arroyo (caudal normal ≥ 1 m³/s) | 115 |
| …con afectación importante: ≥ 50 personas afectadas | 35 |
| **…uno por cantón y temporal (eventos a ≤ 3 días cuentan como uno; queda el de más personas afectadas)** | **32** |

### Por tipo de inundación

| Tipo | Inundaciones |
|---|---:|
| Lluvia intensa (anegamiento) | 20 |
| Desborde de río | 12 |

### Por lluvia del día del evento

La más alta a menos de 5 km medida por el satélite.

| Lluvia | Inundaciones |
|---|---:|
| 30 a 50 mm | 14 |
| 50 a 100 mm | 15 |
| 100 mm o más | 3 |

### Desbordes, según la crecida que alcanzó el río (GEOGLOWS)

| Crecida | Desbordes |
|---|---:|
| Ninguna (no llegó a la de 2 años) | 10 |
| Superó la de 2 años | 2 |

### Por mes

| Mes | Inundaciones |
|---|---:|
| 2026-10 | 1 |
| 2026-09 | 1 |
| 2026-07 | 2 |
| 2026-03 | 13 |
| 2026-02 | 15 |

### Por provincia

| Provincia | Inundaciones |
|---|---:|
| Guayas | 12 |
| El Oro | 7 |
| Los Ríos | 5 |
| Esmeraldas | 4 |
| Santa Elena | 2 |
| Manabí | 2 |

## Archivo completo (todas las inundaciones cruzadas)

| Inundaciones | Cantidad |
|---|---:|
| Completas: con lluvia por satélite y caudal del río (`inundaciones/`, `inundaciones.csv`) | 1620 |
| …con el pronóstico de lluvia del WRF para ese día | 1551 |
| …con el pronóstico de caudal de GEOGLOWS para ese día | 1553 |
| …con pronóstico puntual en una estación del INAMHI a menos de 25 km | 1344 |
| …con la lluvia medida en esa estación (hay mediciones desde oct 2026) | 2 |
| Pendientes: esperan un dato que llegará (`pendientes/`) | 222 |
| Descartadas: nunca tendrán los dos datos (`descartados.csv`) | 1 |

### Descartadas, por motivo

| Motivo | Inundaciones |
|---|---:|
| lluvia por satélite: sin dato en ese lugar; caudal: la simulación de GEOGLOWS llega hasta el 2026-10-16 y se actualiza ~1 vez al mes | 1 |
