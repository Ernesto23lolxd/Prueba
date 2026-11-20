# 🧭 Guía del código de STOCK (pa' nosotros mismos)

> Esto lo escribimos para que **cualquiera del equipo** (o nosotros mismos en 3 meses, que ya no nos vamos a acordar
> de nada 😅) entienda cómo está armado STOCK sin tener que leer 4 mil líneas. Lenguaje relax, pero todo es neta.
> Dentro del código también dejamos comentarios que empiezan con 👉 encima de cada función y variable importante.

---

## 1. La idea en 30 segundos
El tendero le **habla** a la app ("vendí 3 Cocas"), la app manda eso al **servidor**, el servidor le pregunta a la
**IA (Gemini)** qué quiso decir, **valida** lo que contestó la IA (porque la IA a veces alucina), mueve el
**inventario** en la base de datos y le contesta al tendero. Todo lo demás (predicción, surtido, facturas, etc.) son
cálculos sobre ese inventario.

**Regla de oro que nos salvó varias veces:** la IA **propone**, Python **calcula y valida**. Las cuentas de dinero
(costos, precios sugeridos, optimizador) **nunca** las hace la IA.

---

## 2. Mapa de carpetas
```
hackaton_tecno_2026/
├── backend/                 ← el servidor (Python + FastAPI)
│   ├── main.py              ← EL CEREBRO: rutas /api, IA, inventario, facturas, predicción, PIN… (casi todo)
│   ├── basedatos.py         ← hablarle igual a SQLite (laptop) o Postgres/Supabase (nube)
│   ├── seguridad.py         ← ciberseguridad: archivos, IA, límites, IP real, cabeceras
│   ├── acceso.py            ← PIN de la tienda, sesiones y freno anti-adivinanzas
│   ├── privacidad.py        ← el ESCUDO: quita datos sensibles de las facturas antes de la IA
│   ├── cfdi.py              ← leer facturas XML del SAT de forma segura
│   ├── importar.py          ← leer Excel/CSV del tendero aunque venga feo
│   ├── demo_cfdi.xml        ← la factura de ejemplo
│   ├── requirements.txt     ← librerías de Python (con versión fija para que Render no nos sorprenda)
│   └── prueba_*.py          ← nuestras suites de pruebas (ver sección 9)
├── app/                     ← lo que ve el usuario (HTML + Tailwind + JS, sin frameworks)
│   ├── index.html           ← LA APP (/app): todo el JS está aquí abajo, dividido en secciones numeradas
│   ├── inicio.html          ← la portada bonita (/) con el iPhone de muestra
│   ├── privacidad.html      ← Aviso de Privacidad (/privacidad)
│   ├── terminos.html        ← Términos y Condiciones (/terminos)
│   ├── manifest.webmanifest ← para instalarla como app (nombre, ícono, colores)
│   ├── sw.js                ← service worker: que abra sin señal
│   └── iconos/              ← íconos de la app
├── android/                 ← el APK de Android (TWA: envoltorio oficial de Google)
├── .github/workflows/       ← GitHub Actions: compila el APK en la nube
├── docs/                    ← documentación (esta guía, seguridad, despliegue, pruebas, móvil, pitch)
└── render.yaml              ← receta para publicar en Render
```

---

## 3. Qué pasa cuando el tendero dice "vendí 3 Cocas" (el viaje completo)
1. **App (index.html):** `alternarGrabacion()` graba el audio → `enviarAudio()` lo manda a `POST /api/voz`.
2. **Servidor:** el cadenero `ProteccionPin` revisa la cookie del PIN. Sin sesión → 401 y la app pide el PIN.
3. `LimiteGemini` revisa que esa IP no haya usado la IA más de 25 veces en el minuto (si sí → 429 amable).
4. `voz()` revisa que de verdad sea audio (bytes mágicos, no el nombre del archivo) y que no pese más de 10 MB.
5. `preguntar_a_gemini()` arma el prompt: instrucciones (`PROMPT`) + el inventario en texto + el audio.
6. Gemini contesta un JSON tipo `{"acciones": [{"tipo": "venta", "producto": "Coca-Cola 600 ml", "cantidad": 3}]}`.
7. `validar_salida_ia()` (la "aduana") tira todo lo raro: tipos inventados, números negativos, infinitos, etc.
8. `procesar()` → `aplicar_acciones()`: busca el producto con `buscar_producto()` (aunque digan "cocas") y lo
   descuenta **con candado** (si llegan 25 ventas al mismo tiempo, no vende de más).
9. Todo queda en un **lote** con su `antes` y `después` → por eso existe el botón **↩️ Deshacer**.
10. La app recibe la respuesta, la pinta en el chat (`mostrarResultado()`), STOCK la dice en voz alta (`hablar()`)
    y se recarga la pantalla (`cargarTablero()`).

---

## 4. Las tablas de la base de datos
| Tabla | Qué guarda | Ojo con… |
|---|---|---|
| `productos` | nombre, unidad (pieza/kg), cantidad, mínimo, precio, categoría, costo de compra | el nombre es único |
| `movimientos` | cada venta/entrada/ajuste/cambio con `antes`, `despues`, `precio_antes`, `costo_antes`… y su `lote_id` | es lo que permite deshacer exacto |
| `lotes` | cada acción completa (una frase, una factura, un Excel) | `revertido=1` cuando ya se deshizo |
| `cfdi_procesados` | facturas ya sumadas: folio, proveedor, total, forma de pago, archivo y **huella** | evita sumar dos veces la misma |
| `ajustes` | clave/valor: huella del PIN, versión del PIN, secreto de sesión, versión legal aceptada y fecha | **no se borra** con "Empezar de cero" |

En Supabase todas tienen **RLS** (seguridad por filas) activado y sin permisos públicos: aunque alguien consiga la
llave pública de Supabase, no ve nada. Solo nuestro servidor entra.

---

## 5. Los flujos que más nos costaron (y cómo quedaron)

### 🧾 Facturas CFDI (`procesar_factura_xml` / `procesar_factura_pdf`)
1. Huella del archivo → si ya existe, 409 (sin gastar IA).
2. XML: `leer_cfdi()` saca partidas, descuentos, moneda y el tipo. Solo **Ingreso (I)** cuenta como compra.
3. Se separan servicios (flete, renta…) por clave de unidad o clave de producto del SAT (70-95).
4. **Escudo de privacidad:** a la IA solo le mandamos `partidas_minimas()` (cantidad, unidad, descripción, precio).
5. La IA convierte "CAJA C/24" a 24 piezas y empareja "CIEL 1000" con "Agua Ciel 1 L".
6. Python calcula el costo real por pieza `(importe − descuento) × tipo de cambio ÷ piezas`.
7. `escudo_antiinflacion()` compara con el costo anterior: si subió ≥5 % o el margen quedó <15 % → 🚨 y precio sugerido.
8. PDF: lo mismo, pero sacamos el texto aquí con pymupdf, lo limpiamos y solo mandamos renglones de productos.
   PDF escaneado (sin texto) = no se puede limpiar = no se manda a la IA.

### 🔑 PIN (`acceso.py` + sección 11 del JS)
- Primera vez: bienvenida → **aceptar aviso y términos** → crear PIN (dos veces) → adentro.
- El PIN se guarda como huella **scrypt** con sal; la sesión es una cookie **HttpOnly + SameSite=Strict + Secure**
  firmada con HMAC. Si cambias el PIN, sube `pin_version` y todas las sesiones viejas dejan de servir.
- 5 PINs mal por IP (o 30 en total por hora) → 15 min de castigo.
- "Empezar de cero" y "Cargar ejemplo" piden el PIN **otra vez**.
- ¿Olvidó el PIN? En Render: `RESETEAR_PIN=1`, reiniciar, crear uno nuevo y quitar la variable.

### 📜 Aviso de privacidad y términos
- Versión en `acceso.LEGAL_VERSION`. Si cambian los documentos, **súbanle a la versión** y todos tendrán que
  aceptar otra vez al entrar (el servidor guarda versión + fecha como constancia).

### 🎓 Tutorial (sección 9 del JS)
- `PASOS` dice qué sección abrir, qué resaltar y qué texto poner. `seguirFoco()` corre cada cuadro, mueve el foco y
  lo **recorta** para que la tarjeta nunca tape lo que explica. En celular acostado la tarjeta se va a la derecha.

### 📲 App instalable y APK
- `manifest.webmanifest` + `sw.js` = PWA (se instala desde el navegador).
- `android/` = TWA. GitHub Actions lo compila y lo deja en Releases (tag `apk`).
- `/.well-known/assetlinks.json` (en main.py) + la huella de la firma = el APK abre **sin** barra de navegador.

---

## 6. Variables de entorno (en `backend/.env` o en el panel de Render)
| Variable | Para qué | ¿Obligatoria? |
|---|---|---|
| `GEMINI_API_KEY` | la clave de la IA (¡NUNCA a GitHub!) | sí |
| `DATABASE_URL` | Supabase (Session pooler). Vacía = SQLite local | en la nube sí |
| `GEMINI_MODEL` | modelo (por defecto `gemini-3.5-flash-lite`) | no |
| `RATE_LIMIT_POR_MINUTO` | usos de IA por minuto por IP (25; para correr pruebas lo subimos a 400) | no |
| `ALLOWED_ORIGINS` | dominios permitidos (CORS) | no |
| `CONFIAR_PROXY` | `1` en Render para sacar la IP real | en Render sí |
| `INVENTARIO_INICIAL` | `vacio` (default) o `demo` | no |
| `PERMITIR_RESET` | `0` apaga "Empezar de cero" / "Cargar ejemplo" | no |
| `RESETEAR_PIN` | `1` borra el PIN (para cuando lo olvidan) | solo en emergencias |
| `DB_POOL_MAX` | conexiones máximas a Postgres (5) | no |

---

## 7. Correrlo en la laptop
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000     # SIN --reload (OneDrive lo vuelve loco)
```
Abre `http://localhost:8000/app`. Ojo: si `backend/.env` trae `DATABASE_URL` y la red bloquea el puerto 5432 (como la
del evento), no arranca → comenten esa línea con `#` y usa SQLite.

## 8. Publicar
`git push` a `main` y luego en Render **Manual Deploy** (el auto-deploy no nos jaló). Revisar que
`https://stock-tienda.onrender.com/api/salud` diga `"base": "postgres"`.

## 9. Pruebas (todas en `backend/`)
| Archivo | Qué prueba | ¿Necesita servidor? |
|---|---|---|
| `prueba_completa.py` | 32 pruebas de punta a punta (voz real, facturas, Excel, deshacer…) | sí |
| `prueba_auditoria.py` | 26 de ciberseguridad (inyecciones, XXE, archivos trampa, PIN, concurrencia…) | sí |
| `prueba_cfdi.py` | 15 facturas generadas y subidas | sí |
| `prueba_interfaz.py` | la app completa en 12 dispositivos (Playwright) | sí |
| `prueba_movil.py` | app instalable, sin internet, iPhone | sí |
| `prueba_legal.py` | registro con aceptación obligatoria del aviso y términos | sí (simula la tienda) |
| `prueba_privacidad.py` | el escudo: 0 fugas hacia la IA | no |
| `prueba_emparejamiento.py` | el buscador de productos (35 casos) | no |

Las que necesitan servidor entran con el PIN de `STOCK_PIN` (por defecto `246810`). **Ojo:** al entrar mandan
"acepto" el aviso legal; no las corran contra la tienda real de un cliente.

---

## 10. Cosas que nos rompieron la cabeza (para que no te pase)
- **Gemini 2.5 flash daba 404** con nuestra clave → usamos `gemini-3.5-flash-lite`.
- **El cliente de Gemini se cerraba** si no lo guardábamos en una variable.
- **La IA a veces agrega texto antes/después del JSON** → `leer_json()` lo rescata.
- **Ventas simultáneas vendían de más** (17 de 10) → candado de escritura + `FOR UPDATE`.
- **"Agua 600 ml" se emparejaba con "Coca 600 ml"** → el buscador compara números y palabras por separado.
- **La IP se podía falsificar** con `X-Forwarded-For` → usamos la que pone Cloudflare o la última de la cadena.
- **El mismo PDF se sumaba dos veces** si la IA leía distinto el folio → huella SHA-256 del archivo.
- **La red del evento bloquea Postgres (5432/6543)** → pruebas contra Supabase desde Render o con hotspot.
- **OneDrive + `--reload`** = el servidor se reinicia solo a cada rato. Nunca `--reload`.
- **La laptop se queda sin memoria** con servidor + Playwright + Gradle → el APK lo compila GitHub, no nosotros.
- **`\b` en un regex dentro de un string normal de Python = carácter de retroceso** 🤦 → siempre `r"..."`.

## 11. Glosario rápido
- **API:** las rutas `/api/...` del servidor que llama la app.
- **Lote:** una acción completa que se puede deshacer de un jalón.
- **CFDI:** la factura electrónica del SAT (XML + PDF).
- **RLS:** seguridad por filas de Postgres; sin permisos = nadie de fuera ve nada.
- **PWA:** web que se instala como app. **TWA:** la PWA metida en un APK de Android.
- **Prompt injection:** cuando alguien esconde órdenes para la IA en un texto o archivo ("ignora tus reglas…").
- **XXE:** truco de XML para leer archivos del servidor; por eso rechazamos `DOCTYPE`/`ENTITY`.
- **scrypt / HMAC:** cómo guardamos el PIN (huella lenta) y firmamos la sesión (que nadie la falsifique).
