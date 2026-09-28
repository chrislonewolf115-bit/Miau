# finanzas-casa — respaldo del Panel de Ahorro

Respaldo versionado de la base de datos del **Panel de Ahorro**, el dashboard de
finanzas personales que vive como artifact en claude.ai:

<https://claude.ai/artifact/VEjEVT7JPpKXNTCzFou2p5>

El dashboard guarda sus datos en una base de datos propia del artifact (no en un
archivo local) y no expone una API que este repo pueda llamar. Por eso el
respaldo es manual: se exporta un snapshot JSON desde el dashboard y se versiona
aquí.

> ⚠️ **Este repo debe ser PRIVADO.** Los snapshots contienen todos tus movimientos,
> deudas e ingresos. Revisa la visibilidad en GitHub → Settings → General →
> *Danger Zone* → *Change repository visibility* antes de hacer push de datos.

## Estructura

```
data/                    snapshots completos, tal como salen de "Exportar"
  snapshot-AAAA-MM-DD_HHMM.json
  split/                 último snapshot separado por colección (diffs legibles)
    movimientos.json
    obligaciones.json
    cuotas_activas.json
    ingresos.json
    jumbo_categorias.json
    config.json
    _meta.json           exportado_en y archivo de origen
scripts/
  split_snapshot.py      separa un snapshot en data/split/
  validar.py             chequeos de consistencia
```

Solo requiere Python 3.8+ (sin dependencias externas).

## Flujo de respaldo

1. **Exportar.** En el dashboard, clic en **↓ Exportar**. Se descarga
   `panel-ahorro-backup.json` (el nombre es siempre el mismo; la fecha va dentro,
   en `exportado_en`).
2. **Traerlo al repo y separarlo.** Pasa el archivo descargado al script; lo
   copia a `data/` con nombre fechado y regenera `data/split/`:
   ```bash
   python3 scripts/split_snapshot.py ~/Downloads/panel-ahorro-backup.json
   ```
   (Si prefieres moverlo a mano a `data/`, corre el script sin argumentos: usa
   el snapshot más reciente según `exportado_en`.)
3. **Validar.**
   ```bash
   python3 scripts/validar.py
   ```
   Si termina con errores (código de salida 1), corrígelos en el dashboard y
   vuelve a exportar antes de commitear.
4. **Commit y push.**
   ```bash
   git add data/
   git commit -m "Snapshot $(date +%F)"
   git push
   ```
   Luego borra `panel-ahorro-backup.json` de Descargas para que el próximo
   export no quede como `panel-ahorro-backup (1).json`.

`git diff HEAD~1 -- data/split/` muestra qué cambió entre dos respaldos.

## Restaurar

En el dashboard, **↑ Importar** y elige cualquier `data/snapshot-*.json`.

> ⚠️ **Limitación actual del botón Importar** (según el código del artifact):
> - Solo restaura **`movimientos`** y **`config`**. `obligaciones`,
>   `cuotas_activas`, `ingresos` y `jumbo_categorias` se ignoran.
> - Cada movimiento se inserta con un id nuevo, **sin borrar los existentes**:
>   importar sobre una base que ya tiene datos los duplica. `validar.py` avisa
>   de documentos idénticos repetidos para detectar esto.
>
> Hasta que el dashboard soporte una restauración completa, las otras
> colecciones se pueden recargar pidiéndole a Claude que las escriba en la base
> del artifact a partir de `data/split/<coleccion>.json`.

## Esquema

Formato del snapshot:

```json
{
  "exportado_en": "2026-09-28T19:30:00.000Z",
  "movimientos": [...],
  "obligaciones": [...],
  "cuotas_activas": [...],
  "ingresos": [...],
  "jumbo_categorias": [...],
  "config": {...}
}
```

El export **no incluye el id interno** de cada documento (el dashboard lo quita).
Meses son `"AAAA-MM"`, fechas `"AAAA-MM-DD"`, montos en CLP.

### movimientos
Gastos individuales de tarjeta o efectivo.

| campo | tipo | notas |
|---|---|---|
| `fecha` | `"AAAA-MM-DD"` | |
| `mes` | `"AAAA-MM"` | debe coincidir con `fecha` |
| `tarjeta` | `"Bci"` \| `"Cencosud"` \| `"Efectivo"` | |
| `comercio` | string | |
| `monto` | número > 0 | |
| `cuota_actual`, `cuota_total` | entero o `null` | ambos o ninguno |
| `categoria` | string | ver lista en el dashboard (agrupadas en Vivienda, Auto, Supermercado…) |
| `recurrente` | bool | `false` = compra puntual, no cuenta en la línea base del súper |
| `reembolsado` | bool | `true` = lo pagó un tercero, no cuenta en el gasto variable |
| `notas` | string | |

### obligaciones
Deudas fijas de largo plazo (dividendo hipotecario, crédito automotriz).

| campo | tipo | notas |
|---|---|---|
| `nombre` | string | |
| `tipo` | string | |
| `monto_ref` | número | cuota mensual |
| `cuota_actual_ref` | entero | número de cuota en `mes_referencia` |
| `cuota_total` | entero | |
| `mes_referencia` | `"AAAA-MM"` | |
| `fecha_termino` | string | |

### cuotas_activas
Compras en cuotas de tarjeta vigentes; el dashboard las proyecta hacia adelante
desde `mes_referencia`.

| campo | tipo |
|---|---|
| `descripcion` | string |
| `monto_mensual` | número |
| `tarjeta` | string |
| `cuota_actual_ref` | entero (≤ `cuota_total`) |
| `cuota_total` | entero |
| `mes_referencia` | `"AAAA-MM"` |

### ingresos

| campo | tipo | notas |
|---|---|---|
| `nombre` | string | |
| `monto` | número | mensual |
| `fecha_inicio` | `"AAAA-MM"` | |
| `fecha_termino` | `"AAAA-MM"` o `null` | `null` = indefinido |

### jumbo_categorias
Desglose de boletas de supermercado Jumbo por tipo de producto.

| campo | tipo | notas |
|---|---|---|
| `boleta` | string | identificador de la boleta |
| `fecha` | `"AAAA-MM-DD"` | |
| `mes` | `"AAAA-MM"` | |
| `categoria` | string | Carnes y aves, Lácteos y huevos, Limpieza, … |
| `recurrente` | bool | |
| `monto` | número | |

### config
Un solo documento con los parámetros del modelo:

| campo | notas |
|---|---|
| `linea_base_variable` | gasto variable mensual supuesto cuando un mes no tiene movimientos |
| `recortes` | `{moderado, conservador, agresivo}`: recorte mensual por escenario |
| `ahorro_inicial`, `fecha_ahorro_inicial` | punto de partida de la proyección |
| `vacaciones_2027_activas`, `vacaciones_monto` | gasto extraordinario en dic-2027 |
| `objetivo_discrecional` | tope mensual de gasto discrecional |
| `meta_pie_casa` | meta de ahorro para el pie (o `null`) |

## Qué revisa `validar.py`

**Errores** (código de salida 1):
- `cuotas_activas` y `obligaciones`: `1 ≤ cuota_actual_ref ≤ cuota_total`, enteros, `mes_referencia` válido, monto > 0.
- `movimientos`: fecha/mes válidos y consistentes, monto > 0, `recurrente`/`reembolsado` booleanos, cuotas en rango.
- `doc_id` / `_id` duplicados en cualquier colección (si el snapshot los trae).
- `ingresos`: `fecha_inicio`/`fecha_termino` en formato `AAAA-MM` y en orden.
- `config`: campos numéricos y los tres escenarios de recorte.

**Advertencias**:
- Documentos idénticos repetidos (probable doble importación).
- Movimientos `reembolsado=true` que igual entrarían a una línea base:
  marcados `recurrente=true`, o de supermercado sin `recurrente=false`
  (la vista *Súper* del dashboard no mira `reembolsado`).
- Boletas de `jumbo_categorias` sin un movimiento de supermercado ese día.

Además imprime el gasto variable por mes excluyendo reembolsados, para
compararlo con lo que muestra el dashboard.
