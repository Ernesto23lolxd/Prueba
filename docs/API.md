# 🔌 API de STOCK

Todas las rutas `/api/...` (salvo `/api/salud` y `/api/acceso/*`) exigen la **sesión del PIN** de la tienda: una cookie
`stock_sesion` (HttpOnly, SameSite=Strict, Secure) que se obtiene al crear o escribir el PIN. Sin ella responden
**401** con `{"codigo": "pin_requerido"}`. Las rutas con IA tienen un límite de peticiones por minuto por IP (**429**).

## Acceso
| Método | Ruta | Para qué |
|---|---|---|
| GET | /api/acceso/estado | `configurado`, `sesion`, `legal_version`, `legal_aceptado` |
| POST | /api/acceso/crear | `{"pin": "482915", "acepto_legal": "<versión>"}`: primera vez. Sin aceptar el aviso y los términos → **428** |
| POST | /api/acceso/entrar | `{"pin": "...", "acepto_legal": "<versión>"}`: 5 intentos fallidos → **429** por 15 min |
| POST | /api/acceso/cambiar | `{"actual": "...", "nuevo": "..."}`: cierra las demás sesiones |
| POST | /api/acceso/salir | Bloquear (borra la cookie) |

## Inventario e IA
| Método | Ruta | Para qué |
|---|---|---|
| POST | /api/voz | Audio (campo `audio`, máx. 10 MB) → IA → acciones en el inventario. Devuelve `lote_id` |
| POST | /api/texto | `{"texto": "..."}` → igual que voz. Entiende "tengo $1,000, ¿qué compro?" |
| POST | /api/foto | Imagen (`imagen`, máx. 10 MB) + `modo` = ticket / anaquel |
| POST | /api/cfdi | Factura (`archivo` .xml o .pdf, máx. 5 MB): escudo de privacidad, cajas → piezas, costo real y `alertas_precio`. Repetida → **409** |
| POST | /api/cfdi/demo | Procesa la factura de ejemplo |
| POST | /api/importar | Excel/CSV (`archivo`, máx. 5 MB) + `confirmar` = false (vista previa) / true |
| POST | /api/ajuste-rapido | `{"producto_id": 1, "delta": -1}` (botones − / +) |
| PATCH | /api/productos/{id} | Corrige `nombre`, `cantidad`, `minimo`, `precio` o `costo_compra` (se puede deshacer) |
| DELETE | /api/productos/{id} | Borra el producto y su historial |
| POST | /api/lotes/{lote_id}/deshacer | Revierte todo lo que hizo esa acción. Dos veces → **409** |

## Decisiones de compra
| Método | Ruta | Para qué |
|---|---|---|
| GET | /api/tablero | Todo lo de la pantalla en una llamada: predicción, KPIs, lista y movimientos |
| GET | /api/prediccion | Cuándo se acaba cada producto y cuánto comprar |
| GET | /api/lista-compras | Pedido agrupado por proveedor + enlaces de WhatsApp |
| POST | /api/optimizar-presupuesto | `{"presupuesto": 1000}` → qué comprar sin pasarse, sobrante y qué NO comprar |
| POST | /api/promo-rescate | `{"producto_id": 18}` → promo para WhatsApp de lo que no se vende |
| GET | /api/resumen | Valor del inventario, efectivo a apartar, dinero congelado |
| GET | /api/resumen-mes | Lo vendido, lo surtido con facturas, lo más vendido y el dinero parado del mes |
| GET | /api/resumen-mes/csv | `resumen_mensual_stock.csv` para el contador |
| GET | /api/movimientos | Historial |

## Sistema
| Método | Ruta | Para qué |
|---|---|---|
| GET | /api/salud | Estado del servidor y de la base (`sqlite` o `postgres`) |
| POST | /api/reset | `{"modo": "vacio" \| "demo", "pin": "..."}`: borra todo (el PIN se conserva). Se apaga con `PERMITIR_RESET=0` |
| GET | /privacidad · /terminos | Aviso de Privacidad y Términos y Condiciones |
| GET | /manifest.webmanifest · /sw.js | App instalable (PWA) |
| GET | /.well-known/assetlinks.json | Verificación del APK de Android |
