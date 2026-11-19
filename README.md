# 🛒 Surtí — Inventario por voz

El dueño del negocio le habla al celular ("vendí 3 Cocas", "llegaron 10 kilos de frijol",
"¿qué se me está acabando?") y Surtí actualiza el inventario, responde en voz alta y avisa
en una pantallita de mostrador (ESP32) cuando algo se está acabando.

## Estructura
```
backend/   Python + FastAPI + SQLite + Gemini   (Braulio)
app/       HTML + CSS + JavaScript puro          (Sebas y Ernesto)
esp32/     Arduino: OLED + semáforo de LEDs      (Jorge)
```

## Correr el backend
```powershell
cd backend
pip install -r requirements.txt
$env:GEMINI_API_KEY="TU_CLAVE"
python -m uvicorn main:app --host 0.0.0.0 --port 8000
# (sin --reload: con OneDrive no detecta los cambios; si cambias el código, Ctrl+C y vuelve a correrlo)
```
Abrir **http://localhost:8000** en la laptop.

## ⚠️ Micrófono en el celular
El navegador solo deja usar el micrófono en **localhost** o con **HTTPS**.
Para probar en el celular, usa un túnel HTTPS (en otra terminal):
```powershell
npx localtunnel --port 8000      # o: cloudflared tunnel --url http://localhost:8000
```
y abre en el celular la URL https que te da.

## Endpoints
| Método | Ruta | Para qué |
|---|---|---|
| POST | /api/voz | Audio (campo `audio`) → IA → acciones en el inventario |
| POST | /api/texto | `{"texto": "..."}` → igual que voz (respaldo) |
| GET | /api/inventario | Lista de productos con su estado (ok / atencion / bajo / agotado) |
| GET | /api/alertas | Solo los que se están acabando |
| GET | /api/movimientos | Historial |
| GET | /api/esp32 | Resumen corto para la OLED |
| POST | /api/reset | Reinicia los datos de demo |

## ESP32
1. Arduino IDE → Gestor de tarjetas → "esp32 by Espressif" → placa "ESP32 Dev Module".
2. Bibliotecas: Adafruit SSD1306, Adafruit GFX, ArduinoJson.
3. En `esp32/inventario_voz/inventario_voz.ino` cambia WiFi y la IP de la laptop (`ipconfig`).
4. La laptop y el ESP32 deben estar en el **mismo hotspot**.
