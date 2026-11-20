# 🚀 Publicar STOCK en internet (Supabase + Render)

- **GitHub** guarda el código (rama `main`).
- **Supabase** es la base de datos Postgres en la nube (los datos ya no viven en la laptop).
- **Render** toma el código de GitHub y lo publica en `https://stock-tienda.onrender.com`; cada push a `main`
  se vuelve a publicar solo.

> GitHub Pages no sirve aquí: solo publica páginas fijas y STOCK necesita su backend en Python (IA, facturas,
> base de datos). Render es gratis y se conecta directo al repo de GitHub.

Sin `DATABASE_URL` todo sigue funcionando igual que antes con SQLite local (útil para desarrollar y probar).

---

## 1. Supabase (base de datos)
1. Entra a **supabase.com** → **New project**.
   - Nombre: `stock`. Región: **East US (Ohio)** o **West US (Oregon)** (cerca de Render = más rápido).
   - Guarda la **contraseña de la base de datos** (no es la de tu cuenta).
2. Ya creado: botón **Connect** (arriba) → pestaña **Connection string** → **URI** → elige
   **Session pooler** (funciona en redes IPv4, como Render). Se ve así:
   ```
   postgresql://postgres.abcdefghijkl:[TU-CONTRASEÑA]@aws-0-us-east-2.pooler.supabase.com:5432/postgres
   ```
   Cambia `[TU-CONTRASEÑA]` por la contraseña del paso 1 (si tiene símbolos como `@` o `#`, mejor crea una
   contraseña solo con letras y números).
3. **No hay que crear tablas a mano**: STOCK las crea solo la primera vez que arranca (y carga la tienda demo).
   También les activa *Row Level Security* para que la API pública de Supabase no pueda leerlas.

### Probar Supabase desde la laptop (antes de Render)
1. En `backend/.env` agrega la línea (no se sube a GitHub):
   ```
   DATABASE_URL=postgresql://postgres.xxxx:CONTRASEÑA@aws-0-us-east-2.pooler.supabase.com:5432/postgres
   ```
2. Arranca el servidor; en la consola debe decir `Base de datos: Postgres (DATABASE_URL)`.
3. Abre `http://localhost:8000/api/salud` → `{"ok": true, "base": "postgres"}`.
4. Corre las pruebas: `python prueba_completa.py` (con `RATE_LIMIT_POR_MINUTO=150` en el servidor).
5. En Supabase → **Table Editor** ya verás `productos`, `movimientos`, `lotes` y `cfdi_procesados`.

## 2. Render (hosting)
1. Entra a **render.com** con tu cuenta de GitHub.
2. **New → Blueprint** → elige el repo `Ernesto23lolxd/Prueba` → Render lee `render.yaml`.
3. Te pedirá los secretos:
   - `GEMINI_API_KEY`: la clave de Gemini.
   - `DATABASE_URL`: la del paso 1.2.
4. **Apply / Deploy**. En unos minutos queda en `https://stock-tienda.onrender.com`
   (si ese nombre ya existe, Render usa otro: entonces cambia `ALLOWED_ORIGINS` en el panel de Render).
5. Revisa: `https://…onrender.com/api/salud` → `"base": "postgres"`.

## ⚠️ Antes de presentar
- **Render gratis se duerme** tras ~15 min sin visitas: la primera carga tarda ~1 minuto. Ábrelo 2 minutos
  antes de presentar.
- **Supabase gratis se pausa** tras ~7 días sin uso: si pasa, entra al panel y dale *Restore*.
- **La app arranca en ceros** y la primera vez muestra la bienvenida y el tutorial (se repite con el botón **?**).
- **Menú ⋯** → *Cargar tienda de ejemplo* (20 productos con 2 semanas de ventas, para presumir predicción, alertas y
  dinero parado ante el jurado) o *Empezar de cero*. Cuando sea una tienda real, pon `PERMITIR_RESET=0` en Render.
- **Sin cuentas de usuario todavía:** cualquiera con el enlace puede usar la app. Para la demo está bien; para
  una tienda real, el siguiente paso es agregar inicio de sesión.

## Variables de entorno
| Variable | Para qué | Dónde |
|---|---|---|
| `GEMINI_API_KEY` | IA (obligatoria) | `.env` local / secreto en Render |
| `DATABASE_URL` | Postgres de Supabase (sin ella usa SQLite local) | `.env` local / secreto en Render |
| `GEMINI_MODEL` | Modelo de Gemini (por defecto `gemini-3.5-flash-lite`) | opcional |
| `ALLOWED_ORIGINS` | Dominios permitidos (CORS), separados por coma | `render.yaml` |
| `CONFIAR_PROXY` | `1` en Render: el límite por IP usa la IP real del usuario | `render.yaml` |
| `RATE_LIMIT_POR_MINUTO` | Peticiones a la IA por minuto por IP (25) | `render.yaml` |
| `INVENTARIO_INICIAL` | `vacio` (por defecto): la tienda arranca en ceros · `demo`: con la tiendita de ejemplo | `render.yaml` |
| `PERMITIR_RESET` | `0` desactiva "Empezar de cero" y "Cargar tienda de ejemplo" | `render.yaml` |
| `DB_POOL_MAX` | Conexiones máximas a Postgres (5) | opcional |
