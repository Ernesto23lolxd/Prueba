# 📲 STOCK en el celular

STOCK es una **app instalable (PWA)**: se instala desde el navegador, sin Play Store ni App Store.
Queda con **su ícono en la pantalla de inicio**, abre en **pantalla completa** (sin barra del navegador) y usa el
micrófono, la cámara y los archivos del celular como cualquier app.

**Enlace:** https://stock-tienda.onrender.com/app

## Instalar
### Android (Chrome, Edge o Samsung Internet)
1. Abre el enlace.
2. Menú **⋯** de STOCK → **📲 Instalar en mi celular** → **Instalar**.
   *(O desde el menú ⋮ de Chrome → "Instalar app".)*
3. STOCK aparece en tu pantalla de inicio. Si dejas presionado el ícono, salen accesos directos a **Surtir**,
   **Se acaba** e **Inventario**.

### iPhone y iPad (Safari)
1. Abre el enlace **en Safari**.
2. Toca **Compartir** (el cuadrito con la flecha ⬆️) → **Agregar a pantalla de inicio** → **Agregar**.
   *(En STOCK, menú ⋯ → "📲 Instalar en mi celular" muestra estos mismos pasos.)*

### Computadora (Chrome o Edge)
El ícono de instalar aparece a la derecha de la barra de direcciones.

## Qué se ajustó para el celular
| Tema | Cómo quedó |
|---|---|
| Ícono y nombre | Logo de STOCK (también en versión adaptable para Android) y "STOCK" bajo el ícono |
| Pantalla completa | Sin barra del navegador; colores de la app en la barra de estado |
| Muesca y barra de gestos | El encabezado y la barra de secciones respetan las zonas seguras del iPhone y de Android |
| Teclado | Los campos miden 16 px, así que el iPhone no hace zoom al escribir |
| Sin señal | La app abre igual (última copia guardada) y muestra un aviso. Ventas y facturas necesitan internet, porque el inventario vive en la nube |
| Datos | Nunca se guardan en el celular: siempre son los del servidor (no se mezclan ni quedan viejos) |
| Pantallas | Probada de 320 px (Android chico) a tabletas, y con el celular acostado |

## Probado (`backend/prueba_movil.py`)
- ✅ Manifiesto, 4 íconos, 3 accesos directos e ícono de iPhone
- ✅ Chrome/Edge la consideran **instalable**
- ✅ Service worker activo; **abre sin internet** con estilos y aviso, y se recupera al volver la señal
- ✅ En iPhone: sin zoom al escribir, sin desbordes e instrucciones de instalación de Safari

## ¿Y en Play Store?
Con la PWA lista, se puede empaquetar para Android **sin reescribir nada**: en **pwabuilder.com** se pega el enlace
y genera el paquete para Play Store (TWA). Requiere una cuenta de desarrollador de Google Play (pago único) y
algunos días de revisión, así que es el paso siguiente después del hackatón.

## Para la presentación
- Instalen STOCK **antes** en 1 o 2 celulares del equipo y ábranla una vez con internet.
- Abrir la app desde el ícono, a pantalla completa, se ve mucho más profesional que una página web.
- Recuerden que Render gratis se duerme: ábranla 2 minutos antes.
