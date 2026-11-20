# 📲 STOCK en el celular

STOCK es una **app instalable (PWA)**: se instala desde el navegador, sin Play Store ni App Store.
Queda con **su ícono en la pantalla de inicio**, abre en **pantalla completa** (sin barra del navegador) y usa el
micrófono, la cámara y los archivos del celular como cualquier app.

**Enlace:** https://stock-tienda.onrender.com/app

## 🤖 APK para Android
**Descarga directa:** https://github.com/Ernesto23lolxd/Prueba/releases/download/apk/STOCK.apk

1. Abre el enlace en el celular y descarga `STOCK.apk` (2.5 MB).
2. Ábrelo. Si Android pregunta, permite **"Instalar apps de esta fuente"** (Chrome o el administrador de archivos).
3. Listo: STOCK queda con su ícono y abre a pantalla completa, **sin barra de navegador**.

También está en la app (menú ⋯ → **🤖 Descargar app para Android (APK)**) y en la portada.

| Detalle | Valor |
|---|---|
| Tipo | Trusted Web Activity (TWA): la forma oficial de Google para convertir una PWA en app de Android |
| Paquete | `mx.stock.tienda` · versión 1.0 · Android 5.0 o más nuevo |
| Requisito | Chrome instalado (viene en casi todos los Android); si no hay, abre en otro navegador |
| Verificación | `https://stock-tienda.onrender.com/.well-known/assetlinks.json` (huella de la firma) |
| Firma | Llave de **demostración** del hackatón (`android/stock-demo.keystore`, contraseña pública `android`) |
| Cómo se compila | GitHub Actions (`.github/workflows/android-apk.yml`) en cada cambio a `android/`, o a mano desde la pestaña *Actions* → *APK Android* → *Run workflow* |

> Como la app es la misma web, **cualquier mejora que se publique en Render llega sola al APK** sin reinstalar.
> Para Play Store: crear una llave privada (que NO se sube a GitHub), poner su huella en `assetlinks.json` y
> generar un `.aab` (`gradle bundleRelease`).

## Instalar como PWA (sin APK)
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

## Para la presentación
- Instalen STOCK **antes** en 1 o 2 celulares del equipo y ábranla una vez con internet.
- Abrir la app desde el ícono, a pantalla completa, se ve mucho más profesional que una página web.
- Recuerden que Render gratis se duerme: ábranla 2 minutos antes.
