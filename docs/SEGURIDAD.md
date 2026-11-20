# 🔒 Seguridad en STOCK

## 🔑 PIN de acceso por tienda (`backend/acceso.py`)
| Medida | Detalle |
|---|---|
| Toda la API pide sesión | Sin la sesión del PIN, cualquier ruta de datos responde **401** (solo `/api/salud` y las de entrar son públicas) |
| El PIN no se guarda | Solo su huella **scrypt** con sal aleatoria (tabla `ajustes`, con seguridad por filas en Supabase) |
| Sesión segura | Cookie **HttpOnly** (JavaScript no la lee), **SameSite=Strict** (otro sitio no la usa), **Secure** en HTTPS, firmada con **HMAC-SHA256**, 30 días |
| Cambiar el PIN | Cierra las sesiones de todos los demás celulares (la versión del PIN va dentro de la firma) |
| Contra adivinanzas | 5 intentos fallidos por IP o 30 en total por hora → bloqueo de 15 minutos |
| IP no falsificable | Se usa `CF-Connecting-IP` o el **último** `X-Forwarded-For` (el que agrega el proxy), nunca el primero |
| Acciones peligrosas | "Empezar de cero" y "Cargar tienda de ejemplo" piden el PIN **otra vez**; el PIN no se borra al reiniciar |
| PIN válido | 4 a 6 números; se rechazan los triviales (1234, 0000, 111111…) |
| Registros | El servidor ya no escribe en sus registros los valores recibidos (podían incluir el PIN) |
| Olvido del PIN | El administrador pone `RESETEAR_PIN=1` en Render, reinicia, se crea uno nuevo y quita la variable. Los datos no se tocan |

## 🛡️ Escudo de privacidad de facturas (`backend/privacidad.py`)
**Antes de llamar a Gemini**, el servidor quita todo lo que no sirve para inventariar:
RFC, CURP, nombres y razones sociales, domicilios y códigos postales, correos, teléfonos, cuentas bancarias,
folio fiscal (UUID), sellos digitales, certificados y cadena original. **Minimización:** a la IA solo le llegan
cantidad, unidad, descripción y precios de cada partida.

| Factura | Qué pasa |
|---|---|
| **XML** | Se arma un texto solo con las partidas (sin el nombre del proveedor). El folio, el RFC, el total y la forma de pago se leen en el servidor y **nunca salen** |
| **PDF** | Ya no se manda el PDF. El servidor extrae el texto (pymupdf), quita renglones de nombres, domicilios, sellos, folio, etc., borra lo sensible que quede suelto (incluso notas como "pedido de Juan Pérez, tel …" dentro de una partida) y manda solo los renglones de productos |
| **PDF escaneado** | Si no tiene texto no se puede limpiar, así que **no se manda a la IA**: se pide el XML |
| **Transparencia** | La app le dice al tendero qué se protegió: *"🔒 Antes de usar la IA quité de tu factura: RFC, nombres…"* |

Probado en `backend/prueba_privacidad.py`: cero fugas y ningún producto perdido.


STOCK maneja el inventario y el dinero de una tienda, y recibe archivos (facturas, fotos, audios, Excel) y
texto libre que termina en una IA. Por eso aplicamos **defensa en profundidad**. Todo lo de abajo está
probado en `backend/prueba_completa.py` (pruebas 9, 15, 20, 22, 23 y 30).

| Riesgo | Medida | Dónde |
|---|---|---|
| **XXE / XML bombs ("billion laughs")** | 1) Se rechaza cualquier XML con `<!DOCTYPE` o `<!ENTITY` antes de parsear. 2) Se parsea con `defusedxml` (`forbid_dtd`, `forbid_entities`, `forbid_external`). → **400** | `backend/cfdi.py` |
| **Archivos gigantes** | Lectura por bloques con tope real: 5 MB para XML/PDF/Excel, 10 MB para audio/fotos. Se corta sin cargar todo a memoria. → **413** | `seguridad.leer_limitado` |
| **Archivos disfrazados** | Se valida la **firma real** (magic bytes), no solo la extensión: PDF `%PDF-`, XML `<` (tras BOM/espacios), JPEG/PNG/WebP/HEIC, WebM/Ogg/WAV/MP4/MP3, XLSX (ZIP). → **400** | `seguridad.es_pdf`, `tipo_imagen`, `tipo_audio`… |
| **Nombres de archivo maliciosos** | Nunca se usan en rutas de disco; se sanean (sin `/`, `\`, ni caracteres raros, máx. 80) antes de guardarse en la base. | `seguridad.nombre_seguro` |
| **XSS** | Todo dato dinámico (productos, proveedores, respuestas de la IA, historial) pasa por `escapeHtml`/`escapeHTML` o se inserta con `textContent`. Los enlaces solo se aceptan si empiezan con `https://wa.me/`. | `app/index.html`, `app/app.js`, `app/inicio.html` |
| **Prompt injection** | El texto del usuario y las partidas de facturas/Excel van dentro de `<datos_usuario>…</datos_usuario>`; si el usuario intenta cerrar la etiqueta, se neutraliza. El prompt indica que esos datos nunca son instrucciones. Audios, fotos y PDF llevan el mismo aviso. | `seguridad.datos_usuario`, `REGLA_DATOS` |
| **Salida de la IA manipulada** | Antes de tocar SQLite se valida cada acción: solo tipos permitidos, números finitos y no negativos, `0 ≤ cantidad ≤ 100,000`, `0 ≤ precio ≤ 1,000,000`, textos recortados. Lo inválido se descarta y se avisa. | `seguridad.validar_salida_ia` |
| **Inyección SQL** | 100 % de las consultas con placeholders `?`. Los únicos nombres de columna dinámicos vienen de listas blancas fijas del código (migración y `PATCH`), nunca del usuario. | `backend/main.py` |
| **Abuso de la cuota de Gemini** | Límite en memoria por IP (25/min por defecto, `RATE_LIMIT_POR_MINUTO`) en `/api/voz`, `/api/texto`, `/api/foto`, `/api/cfdi`, `/api/promo-rescate`, `/api/importar`. → **429** con mensaje amable | `seguridad.LimiteGemini` |
| **Clickjacking, sniffing, fugas de URL** | Cabeceras: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Content-Security-Policy` (solo el propio servidor + Tailwind CDN y Google Fonts, `frame-ancestors 'none'`, `object-src 'none'`) y `Permissions-Policy`. | `seguridad.CabecerasSeguridad` |
| **CORS** | Solo los orígenes de `ALLOWED_ORIGINS` (por defecto `localhost:8000`). La app se sirve desde el mismo servidor, así que no necesita más. | `backend/main.py` |
| **Fuga de información en errores** | Manejadores globales: el detalle (traceback, rutas, errores de Gemini) solo va a la consola del servidor; el usuario recibe un mensaje claro y seguro. Documentación automática de la API desactivada. | `backend/main.py` |
| **Secretos** | La clave de Gemini vive solo en `backend/.env` (en `.gitignore`, igual que `inventario.db` y `__pycache__/`). Nunca se envía al navegador. | `.gitignore` |
| **CSV con fórmulas** | Las celdas que empiezan con `=`, `+`, `-` o `@` se neutralizan al exportar el resumen del mes (evita inyección de fórmulas en Excel). | `_celda_csv` |
| **Errores del usuario** | Todo cambio queda en un lote que se puede deshacer en una sola transacción; el borrado de productos pide confirmación. | `/api/lotes/{id}/deshacer` |

## Límites conocidos (honestos)
- El límite por IP vive en memoria: sirve para una sola instancia; con varias habría que usar Redis.
- El PIN protege **una tienda por servidor**. Para muchas tiendas en el mismo servidor hace falta un "id de tienda"
  en cada tabla y que la seguridad por filas filtre por dueño (cuentas completas con Supabase Auth).
- El freno de intentos del PIN también vive en memoria: si el servidor se reinicia, el contador vuelve a cero.
- Las fotos de tickets y anaqueles se mandan a la IA tal cual (no traen datos fiscales del tendero); el escudo de
  privacidad aplica a las facturas CFDI.
- La CSP permite `'unsafe-inline'` porque la interfaz usa scripts y estilos en línea (Tailwind por CDN);
  migrar a archivos estáticos permitiría quitarlo.
