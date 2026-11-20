# API de STOCK

Todas las rutas `/api/...`, salvo `/api/salud` y `/api/acceso/*`, piden la sesión del PIN (cookie `stock_sesion`).
Sin ella responden 401. Las rutas que usan el modelo tienen límite de peticiones por minuto por IP (429).

## Acceso
- `GET /api/acceso/estado`: si hay PIN, sesión y aceptación legal.
- `POST /api/acceso/crear`: crea el PIN; exige aceptar aviso y términos (428 si no).
- `POST /api/acceso/entrar`: entra con el PIN; 5 fallos bloquean 15 minutos.
- `POST /api/acceso/cambiar`: cambia el PIN y cierra otras sesiones.
- `POST /api/acceso/salir`: cierra la sesión.

## Inventario
- `POST /api/voz`: audio (máx. 10 MB) a acciones de inventario.
- `POST /api/texto`: lo mismo con texto.
- `POST /api/foto`: imagen de ticket o anaquel (máx. 10 MB).
- `POST /api/cfdi`: factura XML o PDF (máx. 5 MB). Repetida: 409.
- `POST /api/importar`: Excel o CSV (máx. 5 MB), con vista previa.
- `POST /api/ajuste-rapido`: suma o resta una pieza.
- `PATCH /api/productos/{id}`: corrige nombre, cantidad, mínimo, precio o costo.
- `DELETE /api/productos/{id}`: borra el producto.
- `POST /api/lotes/{lote_id}/deshacer`: revierte una acción completa.

## Decisiones de compra
- `GET /api/tablero`: todo lo de la pantalla principal.
- `GET /api/prediccion`: cuándo se acaba cada producto.
- `GET /api/lista-compras`: pedido por proveedor.
- `POST /api/optimizar-presupuesto`: qué comprar con un presupuesto.
- `POST /api/promo-rescate`: promoción para un producto que no se vende.
- `GET /api/resumen`, `/api/resumen-mes`, `/api/resumen-mes/csv`: resúmenes.
- `GET /api/movimientos`: historial.

## Sistema
- `GET /api/salud`: estado del servidor y la base.
- `POST /api/reset`: borra todo o carga la demo (pide PIN; se apaga con `PERMITIR_RESET=0`).
- `GET /privacidad`, `/terminos`: documentos legales.
