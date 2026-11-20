# Seguridad en STOCK

## PIN por tienda (`backend/acceso.py`)
- Toda la API pide sesión; sin ella responde 401.
- El PIN se guarda solo como huella scrypt con sal.
- La sesión es una cookie HttpOnly, SameSite=Strict y Secure, firmada con HMAC-SHA256.
- Cambiar el PIN cierra las demás sesiones.
- 5 fallos por IP o 30 por hora bloquean 15 minutos.
- Reiniciar la tienda pide el PIN otra vez.
- Si se olvida, el administrador usa `RESETEAR_PIN=1` en Render.

## Privacidad de facturas (`backend/privacidad.py`)
Antes de enviar una factura al modelo se quitan RFC, CURP, nombres, domicilios, correos, teléfonos, cuentas, folio,
sellos y certificados. Solo se envían cantidad, unidad, descripción y precio. Un PDF escaneado sin texto no se envía.

## Otras medidas
- XML: se rechaza `DOCTYPE` y `ENTITY` y se usa `defusedxml`.
- Archivos: tope de tamaño y validación por firma real, no por extensión.
- XSS: todo dato dinámico se escapa.
- Prompt injection: los datos del usuario van delimitados y la salida del modelo se valida antes de tocar la base.
- SQL: todas las consultas son parametrizadas.
- Abuso: límite de peticiones por IP.
- Cabeceras: CSP, HSTS, nosniff, DENY, no-referrer.
- Secretos: solo en `.env`, nunca en el repositorio.
- CSV: se neutralizan fórmulas al exportar.

## Límites conocidos
- Los límites por IP viven en memoria; con varias instancias haría falta Redis.
- Un servidor atiende una sola tienda.
- La CSP permite `unsafe-inline` por el uso de Tailwind por CDN.
