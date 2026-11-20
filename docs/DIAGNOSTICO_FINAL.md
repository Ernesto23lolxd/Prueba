# 🏁 STOCK: diagnóstico final oficial

**Fecha:** 20 de noviembre de 2026 · **Versión:** rama `main` (Render: `https://stock-tienda.onrender.com`)
**Veredicto:** ✅ **LISTA PARA PRESENTAR Y LANZAR COMO PILOTO.** Funciona de punta a punta, en la nube, en
celulares y computadoras, con seguridad, privacidad y documentos legales. Lo que falta para escalar a muchas tiendas
está identificado abajo y no impide presentarla.

---

## 1. Calificación por área
| Área | Estado | Evidencia |
|---|---|---|
| Funcionamiento | ✅ Excelente | 32/32 pruebas de punta a punta (voz real, texto, facturas, Excel, deshacer, optimizador, promo, mes) |
| Facturas CFDI | ✅ Excelente | 15/15 facturas generadas y subidas (XML 4.0/3.3, PDF, USD, descuentos, servicios, notas de crédito, duplicados) |
| Ciberseguridad | ✅ Excelente | 26/26 (inyecciones, XXE, archivos trampa, CORS, rutas, concurrencia, PIN, sesiones falsas, documentos legales) |
| Privacidad | ✅ Excelente | Escudo: 0 fugas de datos sensibles hacia la IA (2/2); aviso de privacidad conforme a la LFPDPPP |
| Legal | ✅ Listo | Aviso de Privacidad y Términos publicados, aceptación obligatoria con constancia (3/3) |
| Interfaz y dispositivos | ✅ Excelente | 12/12 dispositivos: Android 320 px → monitor 2560 px, iPhone, iPad, celular acostado |
| App móvil | ✅ Listo | PWA instalable que abre sin internet (4/4) + APK de Android firmado (2.45 MB) |
| Emparejamiento de productos | ✅ Excelente | 35/35 ("cocas", "COCA-COLA 600ML", "panes bimbo"… sin confundir tamaños ni marcas) |
| Nube (Render + Supabase) | ✅ Estable | Respuestas de 110 a 270 ms, 118 de 512 MB de memoria en reposo, 0 errores en los registros |
| Código y documentación | ✅ Listo | 329 comentarios 👉, guía del código, versiones fijas, 0 secretos en todo el historial de GitHub |

---

## 2. Auditoría de la nube (sin iniciar sesión, para no registrar consentimientos falsos)
| Revisión | Resultado |
|---|---|
| `/api/salud` | `{"ok": true, "base": "postgres"}` |
| Páginas `/`, `/app`, `/privacidad`, `/terminos`, manifiesto, service worker, `assetlinks.json`, íconos | 200, entre 110 y 270 ms |
| Cabeceras de seguridad en todo | nosniff, DENY, CSP, no-referrer, Permissions-Policy y **HSTS** (agregada en esta auditoría) |
| Compresión | Brotli (Cloudflare) |
| HTTP → HTTPS | 301 |
| API sin sesión | 401 (los datos de la tienda no se pueden leer sin PIN) |
| Estado de la tienda | Con PIN, en ceros, aviso y términos **pendientes de aceptar por el dueño** |
| APK | Se descarga (2.45 MB) y es un paquete válido; firma = huella publicada en `assetlinks.json` |
| Memoria | 118 MB de 512 MB (antes llegó a 351 MB con la librería de PDF anterior) |
| Registros | 0 errores y 0 advertencias desde el último despliegue |
| Secretos en GitHub | 0 claves de IA, 0 contraseñas, `.env` y la base local nunca se subieron |

---

## 3. Correcciones hechas en esta auditoría final
| # | Qué | Por qué importa |
|---|---|---|
| 16 | **Librería de PDF ligera** (`pypdf` en vez de `pymupdf`) | `pymupdf` arrastraba `onnxruntime`, `numpy` y modelos que no usamos; durante las pruebas el servidor llegó a **351 de 512 MB**. Ahora reposa en 118 MB y los despliegues son más rápidos |
| 17 | **Versiones fijas** en `requirements.txt` | Un despliegue de último momento ya no puede romperse porque salió una versión nueva de una librería |
| 18 | **HSTS** | El navegador recuerda que STOCK solo se abre por HTTPS |
| 19 | Prueba del bloqueo del PIN más precisa | El freno funcionaba bien; la prueba no consideraba el fallo que deja la prueba anterior |

En total, durante todas las pruebas se encontraron y corrigieron **19 fallas** (ver `docs/REPORTE_PRUEBAS.md`).

---

## 4. Lo que falta para escalar (no impide presentar)
| Tema | Por qué | Siguiente paso |
|---|---|---|
| **Varias tiendas por servidor** | Hoy cada servidor es una tienda (con su PIN) | Agregar un "id de tienda" a cada tabla y que la seguridad por filas filtre por dueño |
| **Plan gratis de Render se duerme** | Tras 15 min sin uso, la primera carga tarda ~1 min | Plan de pago de Render (~7 USD/mes) o abrirla 2 minutos antes de presentar |
| **Respaldos de la base** | Supabase gratis no da respaldos descargables | Plan Pro de Supabase o respaldo diario propio |
| **Firma del APK** | Es una llave de demostración (contraseña pública) | Para Play Store: llave privada fuera de GitHub y nueva huella en `assetlinks.json` |
| **Revisión legal** | Los documentos siguen la ley y describen bien la app | Que un abogado los revise antes de cobrar o de operar con muchas tiendas; completar colonia y C.P. del domicilio |
| **Safari real (iPhone)** | Se probó con el motor de Chrome simulando iPhone | Probar el micrófono en un iPhone de verdad |
| **Auto-deploy de Render** | Los pushes a `main` no publican solos | Publicar con *Manual Deploy* (o reconectar el repo en Render) |

---

## 5. Lista para el día de la presentación
- [ ] Abrir `https://stock-tienda.onrender.com/app` **2 minutos antes** (despierta el servidor).
- [ ] Primera vez: **aceptar el aviso y los términos** (como dueños de la tienda) y entrar con el PIN.
- [ ] **Cambiar el PIN `246810`** en ⋯ → 🔑 Cambiar mi PIN.
- [ ] Para la demo: ⋯ → *Cargar tienda de ejemplo* (pide el PIN); al final, ⋯ → *Empezar de cero*.
- [ ] Tener el APK instalado en 1 Android y la app instalada (PWA) en 1 iPhone.
- [ ] Probar el micrófono en el iPhone real.
- [ ] Demo sugerida: voz → factura de ejemplo (mostrar el aviso 🔒 del escudo y la alerta 🚨) → "Tengo $1,000" → Deshacer.
