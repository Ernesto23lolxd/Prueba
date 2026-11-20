# 📦 STOCK — Inventario por voz para tu tienda

El dueño de la tiendita le habla al celular ("vendí 3 Cocas", "llegaron 10 kilos de frijol",
"¿qué surto y qué no?") y STOCK actualiza el inventario, responde en voz alta, predice qué se
va a acabar, avisa qué NO volver a pedir (dinero parado) y arma el pedido por WhatsApp.
También lee la **factura del proveedor (XML o PDF)** y convierte solita cajas y bultos a piezas
y kilos, lee la foto del ticket, trae el inventario desde Excel y da un **resumen del mes** sencillo.

**100 % software:** solo se necesita el celular o la computadora. Sin aparatos extra.

## Estructura
```
backend/   Python + FastAPI + SQLite + Gemini (IA)
  main.py           API, inventario, predicción, IA
  cfdi.py           lectura de facturas XML (CFDI 3.3 y 4.0) con la librería nativa de Python
  importar.py       importación de Excel / CSV
  demo_cfdi.xml     factura de ejemplo (proveedor ficticio) para la demo
  prueba_completa.py  23 pruebas de punta a punta
app/       inicio.html (portada) · index.html (la app) · clasico.html (respaldo)
demo/      Excel/CSV, audios y factura PDF de ejemplo para probar
```

## Variables en `backend/.env`
```
GEMINI_API_KEY=AIza...            # obligatoria (NO se sube a GitHub)
GEMINI_MODEL=gemini-3.5-flash-lite  # opcional; ese es el valor por defecto
```

## Correr
```powershell
cd backend
pip install -r requirements.txt
# la clave va en backend/.env  ->  GEMINI_API_KEY=AIza...   (NO se sube a GitHub)
python -m uvicorn main:app --host 0.0.0.0 --port 8000
# (sin --reload: con OneDrive no detecta cambios; si cambias el código, Ctrl+C y vuelve a correrlo)
```
- Portada: **http://localhost:8000/**
- App: **http://localhost:8000/app**

## Probar todo
```powershell
cd backend
python prueba_completa.py
```

## ⚠️ Micrófono en el celular
El navegador solo deja usar el micrófono en **localhost** o con **HTTPS**. Para el celular usa un túnel:
`npx localtunnel --port 8000` o `cloudflared tunnel --url http://localhost:8000`.

## Endpoints
| Método | Ruta | Para qué |
|---|---|---|
| POST | /api/voz | Audio (campo `audio`) → IA → acciones en el inventario |
| POST | /api/texto | `{"texto": "..."}` → igual que voz |
| POST | /api/foto | Imagen (`imagen`) + `modo` = ticket / anaquel |
| POST | /api/cfdi | Factura del proveedor (`archivo` .xml o .pdf): convierte cajas/paquetes/bultos a piezas o kg y los suma. Si ya se subió → **409** sin duplicar |
| POST | /api/cfdi/demo | Procesa `backend/demo_cfdi.xml` con un clic (también respeta el 409) |
| GET | /api/resumen-mes | Tu mes en resumen: lo vendido, lo surtido con facturas, lo más vendido, dinero parado y últimas facturas |
| GET | /api/resumen-mes/csv | Descarga `resumen_mensual_stock.csv` para guardar o mandar al contador |
| POST | /api/importar | Excel/CSV (`archivo`) + `confirmar` = false (vista previa) / true |
| POST | /api/ajuste-rapido | `{"producto_id": 1, "delta": -1}` botones − / + |
| GET | /api/tablero | Todo lo de la pantalla: predicción, KPIs, lista y movimientos |
| GET | /api/prediccion | Cuándo se acaba cada producto y cuánto comprar |
| GET | /api/lista-compras | Pedido agrupado por proveedor + enlaces de WhatsApp |
| GET | /api/resumen | Valor del inventario, efectivo a apartar, dinero congelado |
| GET | /api/movimientos | Historial |
| POST | /api/reset | Reinicia los datos de demo (también borra las facturas cargadas) |

## Cómo se lee una factura
- **XML (exacto):** se lee con `xml.etree.ElementTree` (sin instalar nada) → proveedor, total, forma de pago,
  folio fiscal (UUID) y partidas. La IA solo traduce "1 CAJA C/24" a "24 piezas" y empareja con tu inventario.
- **PDF (respaldo):** el PDF se manda a Gemini, que lee las partidas y hace la misma conversión.
- **Sin duplicados:** el folio fiscal se guarda en `cfdi_procesados`; si vuelves a subir la misma, no se suma.
- **Avisos amables, nunca regaños:** si un producto llegó más caro que la vez pasada, o si una compra de más de
  $2,000 se pagó en efectivo, STOCK deja un 💡 tip corto. Sin lenguaje contable ni cálculos de impuestos.
