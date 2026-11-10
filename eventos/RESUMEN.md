# Inundaciones de la SNGR cruzadas con lluvia y caudal

Actualizado el 2026-11-10; se rehace solo en cada cruce. Qué es cada dato: [`GUIA.md`](GUIA.md).

## Selección depurada: **42 inundaciones** (`depurados.csv`)

Cada paso deja solo las que cumplen el criterio. Los umbrales están al inicio de `cruzar_eventos.py` (`DEPURACION_…`): para afinar la selección se cambia un número y el siguiente cruce rehace esta tabla.

| Paso | Quedan |
|---|---:|
| Completas (lluvia por satélite y caudal del río) | 2045 |
| …desde el 2026-01-01 | 1978 |
| …de tipo desborde de río o lluvia intensa (anegamiento) (se quitan colapso de drenaje y oleaje o marea) | 1722 |
| …con afectación verificada por la SNGR (daño en personas, viviendas, cultivos o servicios) | 1001 |
| …con el pronóstico WRF en el lugar de las 3 corridas (mismo día, 1 y 2 días antes) | 929 |
| …con el pronóstico de caudal de las 3 corridas | 924 |
| …con pronóstico puntual en una estación del INAMHI a ≤ 15 km | 521 |
| …con lluvia real el mismo día: el satélite midió ≥ 30 mm | 217 |
| …si fue desborde: el río llevaba ≥ 3 veces su caudal normal y no es un arroyo (caudal normal ≥ 1 m³/s) | 167 |
| …con afectación importante: ≥ 50 personas afectadas | 46 |
| **…uno por cantón y temporal (eventos a ≤ 3 días cuentan como uno; queda el de más personas afectadas)** | **42** |

### Por tipo de inundación

| Tipo | Inundaciones |
|---|---:|
| Lluvia intensa (anegamiento) | 26 |
| Desborde de río | 16 |

### Por lluvia del día del evento

La más alta a menos de 5 km medida por el satélite.

| Lluvia | Inundaciones |
|---|---:|
| 30 a 50 mm | 19 |
| 50 a 100 mm | 18 |
| 100 mm o más | 5 |

### Desbordes, según la crecida que alcanzó el río (GEOGLOWS)

| Crecida | Desbordes |
|---|---:|
| Ninguna (no llegó a la de 2 años) | 12 |
| Superó la de 2 años | 3 |
| Superó la de 5 años | 1 |

### Por mes

| Mes | Inundaciones |
|---|---:|
| 2026-11 | 1 |
| 2026-10 | 9 |
| 2026-09 | 2 |
| 2026-07 | 2 |
| 2026-03 | 13 |
| 2026-02 | 15 |

### Por provincia

| Provincia | Inundaciones |
|---|---:|
| Guayas | 14 |
| El Oro | 10 |
| Esmeraldas | 7 |
| Los Ríos | 6 |
| Santa Elena | 2 |
| Manabí | 2 |
| Bolívar | 1 |

## Archivo completo (todas las inundaciones cruzadas)

| Inundaciones | Cantidad |
|---|---:|
| Completas: con lluvia por satélite y caudal del río (`inundaciones/`, `inundaciones.csv`) | 2045 |
| …con el pronóstico de lluvia del WRF para ese día | 1966 |
| …con el pronóstico de caudal de GEOGLOWS para ese día | 1978 |
| …con pronóstico puntual en una estación del INAMHI a menos de 25 km | 1701 |
| …con la lluvia medida en esa estación (hay mediciones desde oct 2026) | 63 |
| Pendientes: esperan un dato que llegará (`pendientes/`) | 96 |
| Descartadas: nunca tendrán los dos datos (`descartados.csv`) | 2 |

### Descartadas, por motivo

| Motivo | Inundaciones |
|---|---:|
| lluvia por satélite: sin dato en ese lugar; caudal: la simulación de GEOGLOWS llega hasta el 2026-10-16 y se actualiza ~1 vez al mes | 2 |
