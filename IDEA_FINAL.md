# 🛒 Surtí — El inventario que se cuenta solo

**Categoría:** Control de inventarios en pequeños negocios (con un toque de Administración de pedidos)
**Pregunta del reto:** ¿Cómo podría un negocio pequeño saber qué se le está acabando?
**Usuario:** la tiendita de barrio / micronegocio de la ciudad de Durango.

## Problema
- 95 % de los negocios de Durango son micro; 2 de cada 3 no usan internet y solo 1 % de los conectados usa IA (INEGI CE 2024).
- 35.5 % de los negocios de Durango cerró entre 2019 y 2021, más que el promedio nacional.
- El tendero lleva el inventario "de memoria" o en libreta: se le acaba lo que más vende (pierde ventas), compra de más lo que no sale (pierde dinero) y no tiene tiempo de usar un Excel.

## Solución: 2 piezas
### 1. App web en el celular (gratis)
| Función | Cómo funciona |
|---|---|
| 📸 Foto del anaquel | Gemini reconoce productos y cuenta piezas → actualiza inventario |
| 🎙️ Venta por voz | "Vendí 3 Cocas y 2 Sabritas" → Gemini lo entiende y descuenta |
| 🧾 Foto del ticket del proveedor | Gemini lee la nota y suma lo que llegó |
| 🚦 Semáforo de existencias | Verde / amarillo / rojo por producto |
| 📈 Predicción | "Al ritmo de esta semana, el huevo se te acaba el sábado" |
| 🛍️ Lista de surtido / pedido | Arma sola la lista de compras al proveedor (la puede mandar por WhatsApp) |
| 📲 NFC | Acercas el celular a la etiqueta del estante → abre la ficha del producto |

### 2. Estante inteligente (~300 MXN)
ESP32 + sensor ultrasónico + OLED + LEDs + botón (+ humedad y servo si da tiempo).
- Mide cuánto queda en el espacio del estante y lo manda por WiFi.
- OLED: "Coca 600: 4 pzas ⚠️ Surtir". LED semáforo.
- Botón "vendí 1" para registrar ventas sin sacar el celular.
- (Extra) Sensor de humedad para perecederos; servo que levanta una banderita de "surtir".

## Arquitectura
```
[Estante ESP32] --WiFi/HTTP--> [Backend FastAPI + BD] <--> [Gemini API]
                                      ↕
                         [App web React en el celular]
```

## Modelo de negocio
- App gratis (freemium); plan Pro ~99 MXN/mes con predicción y pedidos automáticos.
- Estante inteligente ~300 MXN, o en comodato con el plan Pro.
- Aliados: proveedores/distribuidores (les conviene que la tienda nunca se quede sin su producto), CANACO / Secretaría de Desarrollo Económico de Durango.

## Demo (3 minutos)
1. Estante con producto: se quitan piezas → el LED pasa a rojo, OLED dice "Surtir", llega alerta a la app.
2. Foto del anaquel → la IA cuenta los productos.
3. "Vendí 2 Cocas" por voz → baja el inventario.
4. La app muestra la predicción y genera la lista de surtido.

## Roles
- **Braulio:** backend + Gemini (foto, voz, ticket, predicción).
- **Jorge:** soldar ESP32, estante físico, firmware.
- **Ernesto:** app (pantallas de inventario y pedido) + pitch.
- **Sebas:** app (diseño, semáforo, dashboard) + identidad visual.
