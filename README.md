# 📦 STOCK — Inventario por voz para tu tienda

El dueño de la tiendita le habla al celular ("vendí 3 Cocas", "llegaron 10 kilos de frijol",
"¿qué surto y qué no?") y STOCK actualiza el inventario, responde en voz alta, predice qué se
va a acabar, avisa qué NO volver a pedir (dinero congelado) y arma el pedido por WhatsApp.
También lee la foto del ticket del proveedor y trae el inventario desde el Excel que ya tienen.

## Estructura
```
backend/   Python + FastAPI + SQLite + Gemini (IA)
app/       inicio.html (portada) · index.html (la app) · clasico.html (respaldo)
demo/      Excel/CSV y audios de ejemplo para probar
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
| POST | /api/importar | Excel/CSV (`archivo`) + `confirmar` = false (vista previa) / true |
| POST | /api/ajuste-rapido | `{"producto_id": 1, "delta": -1}` botones − / + |
| GET | /api/tablero | Todo lo de la pantalla: predicción, KPIs, lista y movimientos |
| GET | /api/prediccion | Cuándo se acaba cada producto y cuánto comprar |
| GET | /api/lista-compras | Pedido agrupado por proveedor + enlaces de WhatsApp |
| GET | /api/resumen | Valor del inventario, efectivo a apartar, dinero congelado |
| GET | /api/movimientos | Historial |
| POST | /api/reset | Reinicia los datos de demo |
