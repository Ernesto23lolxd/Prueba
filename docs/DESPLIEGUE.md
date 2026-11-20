# Despliegue (Supabase y Render)

GitHub guarda el código, Supabase la base de datos Postgres y Render publica la app en
https://stock-tienda.onrender.com. Sin `DATABASE_URL` la app usa SQLite local.

## Supabase
1. Crear un proyecto en supabase.com (región en EE. UU., cerca de Render).
2. En Connect, copiar la URI del Session pooler y poner la contraseña de la base.
3. Las tablas se crean solas al primer arranque, con seguridad por filas activada.

## Render
1. New, Blueprint, elegir el repositorio (Render lee `render.yaml`).
2. Capturar los secretos `GEMINI_API_KEY` y `DATABASE_URL`.
3. Desplegar y revisar que `/api/salud` responda `"base": "postgres"`.

Los pushes a `main` no se publican solos: usar Manual Deploy.

## Antes de presentar
- Render gratis se duerme tras 15 minutos: abrir la app 2 minutos antes.
- Supabase gratis se pausa tras 7 días sin uso: restaurarlo desde el panel.
- En una tienda real, poner `PERMITIR_RESET=0`.

## Variables de entorno
- `GEMINI_API_KEY`: clave del modelo (obligatoria).
- `DATABASE_URL`: Postgres de Supabase.
- `GEMINI_MODEL`: modelo (por defecto `gemini-3.5-flash-lite`).
- `ALLOWED_ORIGINS`: dominios permitidos (CORS).
- `CONFIAR_PROXY`: `1` en Render para usar la IP real.
- `RATE_LIMIT_POR_MINUTO`: peticiones por minuto por IP (25).
- `INVENTARIO_INICIAL`: `vacio` o `demo`.
- `PERMITIR_RESET`: `0` desactiva el reinicio.
- `RESETEAR_PIN`: `1` borra el PIN si se olvida.
- `DB_POOL_MAX`: conexiones máximas a Postgres (5).
