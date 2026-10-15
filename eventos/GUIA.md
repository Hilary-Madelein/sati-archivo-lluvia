# Guía de los datos: inundaciones cruzadas con lluvia y caudal

Esta guía explica qué tiene cada archivo de esta carpeta y qué significa cada
dato de los JSON, para poder leerlos sin conocer el código. Los números del
momento están en [`RESUMEN.md`](RESUMEN.md).

## 1. Qué es "el cruce"

Por cada **inundación que registró la SNGR** (Secretaría de Gestión de Riesgos),
se buscan, para **ese lugar y ese día**:

1. **La lluvia que cayó**, medida por el satélite PERSIANN y, desde octubre de
   2026, por la estación del INAMHI más cercana.
2. **La lluvia que se había pronosticado**, según el modelo WRF del INAMHI, el
   mismo día, 1 día antes y 2 días antes.
3. **El caudal del río más cercano**, según el modelo GEOGLOWS: cuánto llevaba,
   si era una crecida y cuánto se había pronosticado.

Así, cada evento junta **lo que pasó** (inundación, lluvia medida, caudal) con
**lo que se pronosticaba** (lluvia y caudal), para ver si el pronóstico lo
anticipaba.

Hay dos niveles:

- **Archivo completo** (`inundaciones/`, `inundaciones.csv`): todas las
  inundaciones que tienen, al menos, la lluvia del satélite y el caudal del río.
  Los pronósticos y la estación se guardan si existen; así no se pierde lo medido
  y, si un pronóstico aparece después, se puede agregar.
- **Selección depurada** (`depurados.csv`), **con la que se trabaja**: solo las
  que tienen **todos los pronósticos** (lluvia del WRF y caudal de GEOGLOWS de
  las 3 corridas, y el pronóstico puntual en una estación cercana), además de
  los demás criterios de la sección 6. Una inundación sin pronóstico nunca entra
  a la selección.

## 2. Horarios: el "día de lluvia"

Todas las horas están en **hora de Ecuador** (UTC−5). Cada dato trae su periodo
exacto con `desde` y `hasta`.

| Periodo | Va de… a… | Por qué |
|---|---|---|
| **Día de lluvia** (satélite, estación, evento) | 07:00 a 07:00 del día siguiente | Es como el satélite acumula su lluvia diaria. Un evento a las 19:20 del 11 de octubre usa la lluvia del 11 a las 07:00 al 12 a las 07:00. Un evento de madrugada (antes de las 07:00) cuenta en el día anterior, que es cuando llovió. |
| **Día del WRF** (pronóstico de lluvia) | 02:00 a 02:00 del día siguiente | Es el día que publica el visor oficial del INAMHI. Va 5 h antes que el del satélite: casi el mismo día, no exactamente. |
| **Caudal** | El día del evento y el siguiente | Un río tarda horas en crecer después de la lluvia, así que se toma lo más alto de los dos días. |

## 3. Archivos

| Archivo | Qué tiene |
|---|---|
| `RESUMEN.md` | Cuántas inundaciones hay y cuántas quedan en cada paso de la depuración. |
| `depurados.csv` | **La selección con la que se trabaja**: las inundaciones que pasan la depuración (ver sección 6). Una fila por inundación, para Excel. |
| `inundaciones.csv` | Todas las inundaciones completas, sin depurar. Mismas columnas. |
| `inundaciones/AAAA/MM/<id>.json` | El detalle de cada inundación completa (sección 4). El nombre del archivo es su `id`. |
| `pendientes/AAAA/MM/<id>.json` | Las que esperan un dato que todavía no existe, casi siempre el caudal: la simulación de GEOGLOWS va ~1 mes atrasada. Se completan solas. |
| `descartados.csv` | Las que nunca podrán tener lluvia y caudal, y por qué. |

## 4. El JSON de cada inundación, bloque por bloque

Cada bloque trae además un campo `que_es` con una explicación corta.

### `evento`: lo que registró la SNGR

| Campo | Qué es |
|---|---|
| `id` | Identificador único (el mismo que usa SATI.EC). |
| `tipo` | Tipo de evento según la SNGR. Casi siempre "Inundación", a secas: el tipo real está en `clasificacion`. |
| `causa` | Causa declarada por la SNGR: "Lluvias intensas", "Desbordamiento de cuerpos de agua"… |
| `fecha`, `hora` | Cuándo ocurrió o se reportó, en hora de Ecuador. |
| `provincia`, `canton`, `parroquia`, `sector` | Dónde. |
| `latitud`, `longitud` | Punto del evento. Todo el cruce se calcula en este punto. |
| `nivel` | Nivel oficial de la SNGR (1 a 4): cuánta respuesta exigió el evento. |
| `estado` | "Cierre" (atendido, cifras finales) o "Seguimiento" (aún en curso; las cifras pueden cambiar). |
| `descripcion` | El relato de la SNGR: qué pasó y dónde. |
| `personas_afectadas`, `familias_afectadas`, `personas_damnificadas`, `personas_evacuadas`, `personas_extraviadas`, `personas_fallecidas` | Personas: afectadas (sufrieron el evento), damnificadas (perdieron su vivienda o medios de vida), evacuadas, extraviadas y fallecidas. |
| `viviendas_afectadas`, `viviendas_destruidas` | Viviendas con daños / perdidas. |
| `puentes_afectados`, `puentes_destruidos`, `escuelas_afectadas`, `centros_de_salud_afectados` | Infraestructura dañada. |
| `hectareas_cultivo_afectadas`, `hectareas_cultivo_perdidas` | Cultivos dañados / perdidos (ha). |

### `clasificacion`: qué tipo de inundación fue

La misma regla que usa SATI.EC, que lee el relato de la SNGR porque esta casi
nunca indica el subtipo.

| Campo | Qué es |
|---|---|
| `tipo` | **Desborde de río** (un río, estero o quebrada salió de su cauce o creció), **Lluvia intensa (anegamiento)** (agua acumulada por la lluvia, sin río), **Colapso de drenaje** (alcantarillas o canales tapados) u **Oleaje o marea**. |
| `codigo` | El mismo tipo en código: `river_flood`, `rain_flood`, `drainage_flood`, `coastal_flood`. |
| `afectacion_verificada` | `true` si la SNGR registró daño en personas, viviendas, cultivos o servicios. Las calles con agua que luego drenó no cuentan. |

### `resumen`

El cruce en una o dos frases. Por ejemplo: *"Satélite: 53,0 mm el día del evento
en el lugar (hasta 105,0 mm a menos de 5 km)… Pronóstico WRF para ese día…
Estación El Carmen (a 5,3 km): el WRF pronosticaba ahí… Río: 0,9 m³/s, 5,6 veces
su caudal normal…"*

### `dia_de_lluvia`

La fecha y el periodo (07:00 a 07:00) que se tomó como "el día del evento" para
la lluvia (sección 2).

### `lluvia_satelite`: la lluvia que cayó, según el satélite

Fuente: satélite **PERSIANN**, servido por el INAMHI. Cubre todo el país, con
celdas de ~4 km.

| Campo | Qué es |
|---|---|
| `dia_del_evento`, `dia_anterior`, `dos_dias_antes` | La lluvia de cada día de lluvia (07:00 a 07:00). |
| `total_3_dias` | La suma de los tres días: el suelo saturado por lluvias anteriores también cuenta. |
| `en_el_lugar_mm` | Lluvia en la celda del punto del evento (mm). |
| `maxima_a_menos_de_5km_mm` | La celda más lluviosa a menos de 5 km (mm). Útil porque el aguacero puede caer cerca y no justo encima. |

**Cuidado:** el satélite suele **quedarse corto** en aguaceros fuertes y cortos;
por eso hay inundaciones con poca lluvia de satélite.

### `lluvia_pronosticada`: lo que pronosticaba el WRF en el lugar

Fuente: modelo **WRF del INAMHI**, la lluvia diaria de su visor oficial.

| Campo | Qué es |
|---|---|
| `periodo` | El día del WRF (02:00 a 02:00). |
| `hecho_el_mismo_dia`, `hecho_1_dia_antes`, `hecho_2_dias_antes` | Lo que pronosticaba la corrida de ese día, la del día anterior y la de dos días antes. Sirve para ver con cuánta anticipación lo vio venir. |
| `corrida_del_modelo` | Cuándo empezó esa corrida. |
| `en_el_lugar_mm`, `maxima_a_menos_de_5km_mm` | Como en el satélite: en la celda del evento y la más alta alrededor. |

### `lluvia_estacion_inamhi`: la estación del INAMHI más cercana

La estación más cercana al evento, a menos de 25 km.

| Campo | Qué es |
|---|---|
| `estacion` | Código, nombre, distancia al evento (km) y coordenadas. |
| `lluvia_medida_dia_del_evento` | Lo que midió su pluviómetro el día de lluvia (07:00 a 07:00). **Solo existe desde el 13 de octubre de 2026**, porque la API del INAMHI no da fechas pasadas. Antes es `null`. |
| `pronostico_puntual` | **Pronóstico puntual**: lo que el WRF pronosticaba en las coordenadas de la estación para el día del WRF, hecho el mismo día (`hecho_el_mismo_dia_mm`), 1 y 2 días antes. `lluvia_medida_mm` es lo que midió la estación en esas mismas 24 h, cuando existe: así se compara pronóstico y medición en el mismo punto y periodo. |

### `caudal_del_rio`: el río más cercano, según GEOGLOWS

Fuente: modelo **GEOGLOWS**, el mismo del Hydroviewer del INAMHI. Es caudal
**simulado** por el modelo, no medido.

| Campo | Qué es |
|---|---|
| `rio_geoglows` | Identificador del tramo de río más cercano al punto del evento. |
| `caudal_dia_del_evento_m3s` | Caudal medio ese día (m³/s). |
| `caudal_maximo_ese_dia_y_el_siguiente_m3s` | El más alto de los dos días, porque el río crece con retraso. |
| `caudal_normal_del_mes_m3s` | El caudal típico de ese río en ese mes: la mediana desde 1980. |
| `veces_el_caudal_normal` | Cuántas veces su caudal normal llevaba el río. Por ejemplo, 5,6 = casi seis veces lo habitual. |
| `umbrales_de_crecida_m3s` | Caudales que el río alcanza en promedio **una vez cada 2, 5, 10, 25, 50 y 100 años** (periodos de retorno, calculados como el Hydroviewer del INAMHI). |
| `crecida_alcanzada_años`, `crecida_alcanzada` | La mayor crecida que superó (0 = ninguna; 2 = la de 2 años…). Superar la de 2 años ya es una crecida. |
| `caudal_pronosticado` | Lo que GEOGLOWS pronosticaba para esos dos días, hecho el mismo día, 1 y 2 días antes: `maximo_promedio_de_ensambles_m3s` (el pronóstico central, promedio de 51 escenarios), `maximo_del_ensamble_mas_alto_m3s` (el escenario más alto) y `maximo_alta_resolucion_m3s` (la corrida más detallada). `fuente` dice si salió de la API de GEOGLOWS o de su archivo en AWS. |

**Cuidado:** el "río más cercano" a veces es un **arroyo o afluente pequeño** y no
el río que se desbordó. Si `caudal_normal_del_mes_m3s` es muy bajo (menos de
1 m³/s) en un desborde grande, probablemente se tomó el tramo equivocado. Ejemplo:
el desborde del río Esmeraldas del 29 de septiembre de 2026 quedó asociado a un
arroyo de 0,2 m³/s.

### `cruce`: cómo quedó el cruce

| Campo | Qué es |
|---|---|
| `completo` | `true` si tiene lluvia del satélite y caudal. |
| `falta` | Qué dato falta y por qué (en pendientes). |
| `estado` | `completo`, `espera` (falta un dato que llegará), `fallo` (una fuente no respondió; se reintenta) o `definitivo`. |
| `procesado` | Cuándo se cruzó por última vez (UTC). |

## 5. Columnas de los CSV

Son los mismos datos, aplanados en una fila por inundación. Los nombres siguen el
JSON, por ejemplo:

- `lluvia_satelite_dia_evento_mm` = `lluvia_satelite.dia_del_evento.en_el_lugar_mm`
- `lluvia_pronosticada_1_dia_antes_mm` = el WRF en el lugar, hecho 1 día antes
- `estacion_pronostico_1_dia_antes_mm` = el pronóstico puntual en la estación, hecho 1 día antes
- `caudal_max_dia_evento_y_siguiente_m3s`, `veces_el_caudal_normal`, `crecida_alcanzada_años`
- `umbral_crecida_2_años_m3s`, …: los umbrales de crecida
- `caudal_pronosticado_mismo_dia_m3s`: el pronóstico central de caudal, hecho ese día
- `tipo_inundacion`, `afectacion_verificada`: la clasificación
- `resumen`, `descripcion_sngr`: el resumen del cruce y el relato de la SNGR

Las unidades van al final del nombre: `_mm` es lluvia en milímetros, `_m3s` es
caudal en metros cúbicos por segundo y `_km` es distancia.

## 6. Depuración: cómo se llega a `depurados.csv`

De todas las inundaciones completas se dejan solo las que sirven para analizar
pronóstico frente a realidad. Cada paso exige una cosa más:

1. **Desde el 1 de enero de 2026.**
2. **Tipo desborde de río o lluvia intensa**: se quitan colapso de drenaje (es un problema de obras) y oleaje.
3. **Afectación verificada** por la SNGR.
4. **Pronósticos completos**: WRF en el lugar y caudal de GEOGLOWS de las tres corridas (mismo día, 1 y 2 días antes).
5. **Estación del INAMHI cercana**, para tener el pronóstico puntual.
6. **Lluvia real el mismo día**: el satélite midió un aguacero fuerte ese día, que es el que se compara con el pronóstico. No basta con que se haya acumulado en 3 días.
7. **Si fue desborde, el río crecido** y que no sea un arroyo.
8. **Afectación importante**: muchas personas afectadas según la SNGR.
9. **Uno por cantón y temporal**: los registros del mismo cantón separados por pocos días son el mismo temporal y cuentan como uno, el de más personas afectadas. Así cada evento de la selección es independiente.

No se exige que el pronóstico haya **acertado**. Si solo quedaran los eventos que
el pronóstico vio venir, no se podría medir cuándo falla. Se exige que los
pronósticos **existan**, y la intensidad se pide en lo que **pasó** (lluvia medida
y caudal).

Los umbrales exactos y cuántas quedan en cada paso están en `RESUMEN.md`. Se
cambian al inicio de `cruzar_eventos.py`, en las constantes `DEPURACION_…`.
