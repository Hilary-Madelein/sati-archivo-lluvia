# Inundaciones de la SNGR cruzadas con lluvia y caudal

Actualizado el 2026-11-07; se rehace solo en cada cruce. Qué es cada dato: [`GUIA.md`](GUIA.md).

## Selección depurada: **35 inundaciones** (`depurados.csv`)

Cada paso deja solo las que cumplen el criterio. Los umbrales están al inicio de `cruzar_eventos.py` (`DEPURACION_…`): para afinar la selección se cambia un número y el siguiente cruce rehace esta tabla.

| Paso | Quedan |
|---|---:|
| Completas (lluvia por satélite y caudal del río) | 1882 |
| …desde el 2026-01-01 | 1815 |
| …de tipo desborde de río o lluvia intensa (anegamiento) (se quitan colapso de drenaje y oleaje o marea) | 1579 |
| …con afectación verificada por la SNGR (daño en personas, viviendas, cultivos o servicios) | 940 |
| …con el pronóstico WRF en el lugar de las 3 corridas (mismo día, 1 y 2 días antes) | 868 |
| …con el pronóstico de caudal de las 3 corridas | 863 |
| …con pronóstico puntual en una estación del INAMHI a ≤ 15 km | 480 |
| …con lluvia real el mismo día: el satélite midió ≥ 30 mm | 187 |
| …si fue desborde: el río llevaba ≥ 3 veces su caudal normal y no es un arroyo (caudal normal ≥ 1 m³/s) | 141 |
| …con afectación importante: ≥ 50 personas afectadas | 38 |
| **…uno por cantón y temporal (eventos a ≤ 3 días cuentan como uno; queda el de más personas afectadas)** | **35** |

### Por tipo de inundación

| Tipo | Inundaciones |
|---|---:|
| Lluvia intensa (anegamiento) | 21 |
| Desborde de río | 14 |

### Por lluvia del día del evento

La más alta a menos de 5 km medida por el satélite.

| Lluvia | Inundaciones |
|---|---:|
| 30 a 50 mm | 16 |
| 50 a 100 mm | 16 |
| 100 mm o más | 3 |

### Desbordes, según la crecida que alcanzó el río (GEOGLOWS)

| Crecida | Desbordes |
|---|---:|
| Ninguna (no llegó a la de 2 años) | 12 |
| Superó la de 2 años | 2 |

### Por mes

| Mes | Inundaciones |
|---|---:|
| 2026-10 | 3 |
| 2026-09 | 2 |
| 2026-07 | 2 |
| 2026-03 | 13 |
| 2026-02 | 15 |

### Por provincia

| Provincia | Inundaciones |
|---|---:|
| Guayas | 13 |
| El Oro | 7 |
| Esmeraldas | 6 |
| Los Ríos | 5 |
| Santa Elena | 2 |
| Manabí | 2 |

## Archivo completo (todas las inundaciones cruzadas)

| Inundaciones | Cantidad |
|---|---:|
| Completas: con lluvia por satélite y caudal del río (`inundaciones/`, `inundaciones.csv`) | 1882 |
| …con el pronóstico de lluvia del WRF para ese día | 1809 |
| …con el pronóstico de caudal de GEOGLOWS para ese día | 1815 |
| …con pronóstico puntual en una estación del INAMHI a menos de 25 km | 1562 |
| …con la lluvia medida en esa estación (hay mediciones desde oct 2026) | 37 |
| Pendientes: esperan un dato que llegará (`pendientes/`) | 214 |
| Descartadas: nunca tendrán los dos datos (`descartados.csv`) | 2 |

### Descartadas, por motivo

| Motivo | Inundaciones |
|---|---:|
| lluvia por satélite: sin dato en ese lugar; caudal: la simulación de GEOGLOWS llega hasta el 2026-10-16 y se actualiza ~1 vez al mes | 2 |
