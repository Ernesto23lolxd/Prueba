# 📦 STOCK — Inventario por voz para tu tienda

El dueño de la tiendita le habla al celular ("vendí 3 Cocas", "llegaron 10 kilos de frijol",
"¿qué surto y qué no?") y STOCK actualiza el inventario, responde en voz alta, predice qué se
va a acabar, avisa qué NO volver a pedir (dinero parado) y arma el pedido por WhatsApp.
También lee la **factura del proveedor (XML o PDF)** y convierte solita cajas y bultos a piezas
y kilos, lee la foto del ticket, trae el inventario desde Excel y da un **resumen del mes** sencillo.

**100 % software:** solo se necesita el celular o la computadora. Sin aparatos extra.

## 🏆 Lo que nos hace diferentes: cuidamos el efectivo y la ganancia
1. **🚨 Escudo anti-inflación:** al subir la factura, STOCK calcula cuánto te costó de verdad cada pieza o
   kilo. Si el proveedor te subió el precio 5 % o más, o si ya casi no le ganas (menos de 15 %), te avisa:
   *"Aguas: tu proveedor te subió el Aceite 1-2-3 de $35 a $41 (+17 %)… Te conviene subirlo a $51"*,
   con un botón para **actualizar el precio en 1 clic**.
2. **💵 "Nomás tengo $X hoy":** dices cuánto efectivo traes y STOCK arma la mejor compra **sin pasarse ni un
   peso**: primero lo que se te acaba mañana, luego lo de 2 días y al final completa el pedido. Te dice cuánto
   te sobra, qué queda pendiente y qué **no** comprarle al preventista. Las cuentas las hace Python, no la IA.
3. **🔥 Rescate de dinero parado:** para lo que casi no se vende, la IA redacta una promo para tu estado de
   WhatsApp o el grupo de vecinos, sin bajar del costo. Botones para copiar o abrir en WhatsApp.

## ↩️ Corregir errores sin miedo
- **Deshacer:** cada acción (voz, texto, foto, factura, Excel, corrección o ajuste) queda en un *lote*. El botón
  **↩️ Deshacer** revierte todo el lote en una sola transacción: regresa existencias, precios y costos, borra los
  productos que se crearon por error y, si era una factura, libera su folio para volver a subir la correcta.
- **Corregir y eliminar:** cada producto tiene **✏️ Corregir** (nombre, existencia, mínimo, precio, costo) y
  **🗑️ Eliminar** (borrado definitivo, con confirmación dentro de la tarjeta).

## Estructura
```
backend/   Python + FastAPI + SQLite + Gemini (IA)
  main.py             API, inventario, predicción, IA, lotes/deshacer, optimizador
  basedatos.py        Postgres (Supabase) o SQLite local con la misma interfaz
  seguridad.py        archivos, prompt injection, validación de la IA, límite por IP y cabeceras HTTP
  cfdi.py             lectura segura de facturas XML (CFDI 3.3 y 4.0) con defusedxml
  importar.py         importación de Excel / CSV
  demo_cfdi.xml       factura de ejemplo (proveedor ficticio) con un aumento de precio para la demo
  prueba_completa.py  31 pruebas de punta a punta
app/       inicio.html (portada) · index.html (la app) · clasico.html (respaldo)
demo/      Excel/CSV, audios y factura PDF de ejemplo para probar
docs/      SEGURIDAD.md (medidas de ciberseguridad)
```

## 🚀 Publicar en internet
Supabase (base de datos) + Render (hosting desde GitHub): paso a paso en [`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md).
Sin `DATABASE_URL`, STOCK usa SQLite local como siempre.

## Variables en `backend/.env`
```
GEMINI_API_KEY=AIza...                 # obligatoria (NO se sube a GitHub)
GEMINI_MODEL=gemini-3.5-flash-lite     # opcional; ese es el valor por defecto
ALLOWED_ORIGINS=http://localhost:8000  # opcional; agrega la URL del túnel si usas uno (separadas por coma)
RATE_LIMIT_POR_MINUTO=25               # opcional; peticiones a la IA por minuto por IP
DATABASE_URL=postgresql://...           # opcional; Supabase. Sin ella usa SQLite local
```

## Correr
```powershell
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
# (sin --reload: con OneDrive no detecta cambios; si cambias el código, Ctrl+C y vuelve a correrlo)
```
- Portada: **http://localhost:8000/**
- App: **http://localhost:8000/app**

## Probar todo
```powershell
cd backend
$env:RATE_LIMIT_POR_MINUTO=150; python -m uvicorn main:app --port 8000   # en una terminal
python prueba_completa.py                                                  # en otra
```
La suite hace muchas llamadas seguidas a la IA; por eso, solo para probar, se sube el límite por minuto.

## ⚠️ Micrófono en el celular
El navegador solo deja usar el micrófono en **localhost** o con **HTTPS**. Para el celular usa un túnel:
`npx localtunnel --port 8000` o `cloudflared tunnel --url http://localhost:8000` (y agrega esa URL a `ALLOWED_ORIGINS`).

## Endpoints
| Método | Ruta | Para qué |
|---|---|---|
| POST | /api/voz | Audio (campo `audio`, máx. 10 MB) → IA → acciones en el inventario. Devuelve `lote_id` |
| POST | /api/texto | `{"texto": "..."}` → igual que voz. Entiende "tengo $1,000, ¿qué compro?" |
| POST | /api/foto | Imagen (`imagen`, máx. 10 MB) + `modo` = ticket / anaquel |
| POST | /api/cfdi | Factura (`archivo` .xml o .pdf, máx. 5 MB): convierte cajas/bultos a piezas o kg, los suma y regresa `alertas_precio`. Repetida → **409** |
| POST | /api/cfdi/demo | Procesa `backend/demo_cfdi.xml` con un clic (también respeta el 409) |
| POST | /api/optimizar-presupuesto | `{"presupuesto": 1000}` → qué comprar sin pasarse, sobrante, pendientes, qué NO comprar y `whatsapp_url` |
| POST | /api/promo-rescate | `{"producto_id": 18}` → mensaje de promo para WhatsApp + `whatsapp_url` |
| POST | /api/lotes/{lote_id}/deshacer | Revierte todo lo que hizo esa acción. Dos veces → **409** |
| PATCH | /api/productos/{id} | Corrige `nombre`, `cantidad`, `minimo`, `precio` o `costo_compra` (se puede deshacer) |
| DELETE | /api/productos/{id} | Borra el producto y su historial por completo |
| GET | /api/resumen-mes | Tu mes en resumen: lo vendido, lo surtido con facturas, lo más vendido, dinero parado y últimas facturas |
| GET | /api/resumen-mes/csv | Descarga `resumen_mensual_stock.csv` para guardar o mandar al contador |
| POST | /api/importar | Excel/CSV (`archivo`, máx. 5 MB) + `confirmar` = false (vista previa) / true (se puede deshacer) |
| POST | /api/ajuste-rapido | `{"producto_id": 1, "delta": -1}` botones − / + |
| GET | /api/tablero | Todo lo de la pantalla: predicción, KPIs, lista y movimientos (con `lote_id`) |
| GET | /api/prediccion | Cuándo se acaba cada producto y cuánto comprar |
| GET | /api/lista-compras | Pedido agrupado por proveedor + enlaces de WhatsApp |
| GET | /api/resumen | Valor del inventario, efectivo a apartar, dinero congelado |
| GET | /api/movimientos | Historial |
| GET | /api/salud | Estado del servidor y de la base de datos (lo usa Render) |
| POST | /api/reset | Reinicia los datos de demo (también borra facturas y lotes) |

## Cómo se lee una factura
- **XML (exacto):** se lee con `defusedxml` → proveedor, total, forma de pago, folio fiscal (UUID) y partidas.
  La IA solo traduce "1 CAJA C/24" a "24 piezas" y empareja con tu inventario; el costo real por pieza
  (importe ÷ piezas) lo calcula Python.
- **PDF (respaldo):** el PDF se manda a Gemini, que lee las partidas y hace la misma conversión.
- **Sin duplicados:** el folio fiscal se guarda en `cfdi_procesados`; si vuelves a subir la misma, no se suma.
- **Servicios fuera:** fletes, estadías o rentas (clave de unidad E48/ACT) no se suman al inventario.
- **Avisos amables, nunca regaños:** sobreprecio del proveedor, margen bajo o compra de más de $2,000 en efectivo.
  Sin lenguaje contable ni cálculos de impuestos.

## 🔒 Seguridad
Resumen (detalle en [`docs/SEGURIDAD.md`](docs/SEGURIDAD.md)): XML blindado contra XXE y XML bombs, archivos
validados por tamaño real y firma (magic bytes), escape de todo dato dinámico en la interfaz, defensa contra
prompt injection y validación estricta de lo que responde la IA, SQL 100 % parametrizado, cabeceras HTTP de
seguridad, límite de peticiones por IP, CORS configurable y errores que nunca exponen detalles internos.
