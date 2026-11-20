# 🔒 Seguridad en STOCK

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
- No hay cuentas de usuario todavía: está pensado para correr en la red de la tienda. El siguiente paso sería
  agregar inicio de sesión antes de exponerlo a internet.
- La CSP permite `'unsafe-inline'` porque la interfaz usa scripts y estilos en línea (Tailwind por CDN);
  migrar a archivos estáticos permitiría quitarlo.
