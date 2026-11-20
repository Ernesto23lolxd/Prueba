# STOCK

Asistente de inventario por voz para la tiendita de barrio. El tendero le habla y STOCK lleva la cuenta: avisa qué se
acaba, qué no volver a pedir y arma el pedido por proveedor.

Hackatón Tecno 2026, Durango, México. Categoría: control de inventarios en pequeños negocios.

- App: https://stock-tienda.onrender.com/app
- APK Android: https://github.com/Ernesto23lolxd/Prueba/releases/download/apk/STOCK.apk

Para los jueces: la tienda de la demo pide PIN (pídanlo al equipo) y aceptar el aviso de privacidad y los términos.
La primera carga puede tardar un minuto porque el servidor gratuito se duerme.

## Problema
En Durango hay 61,400 micronegocios (95 % del total). El 35.5 % de los negocios cerró entre 2019 y 2021, por
mercancía que no se vende, merma, costos que suben y ventas perdidas. Solo el 35.8 % usa internet y el 84.5 % cobra
en efectivo, así que operan sin datos. Fuentes en [docs/investigacion](docs/investigacion/IMPACTO_DURANGO.md).

## Qué hace
- Ventas por voz o texto ("vendí 3 Cocas y 2 Sabritas").
- Lee facturas CFDI (XML o PDF), convierte cajas a piezas y avisa si el proveedor subió el precio.
- Lee fotos de tickets y anaqueles, y Excel o CSV con cualquier formato.
- Predice cuándo se acaba cada producto y arma el pedido por proveedor.
- Reparte un presupuesto ("tengo $1,000") en lo más urgente.
- Detecta mercancía que no se vende y propone una promoción.
- Cualquier acción se puede deshacer.

Funciona en Android, iPhone y computadora, como app instalable (PWA) o APK.

## Arquitectura
App (HTML, Tailwind, JavaScript) -> servidor FastAPI en Render -> Gemini (solo datos de inventario) y Supabase
Postgres. El modelo propone acciones en JSON; Python las valida y hace todas las cuentas de dinero.

## Seguridad y privacidad
PIN por tienda, sesión en cookie segura, limpieza de datos personales de las facturas antes de enviarlas al modelo,
defensa contra inyecciones y archivos maliciosos, y aviso de privacidad conforme a la LFPDPPP. Detalle en
[docs/SEGURIDAD.md](docs/SEGURIDAD.md).

## Modelo de negocio
- Barrio: gratis con anuncios locales.
- Tiendita: $169 al mes (plan principal).
- Negocio Pro: $329 al mes.
- Ultra: $649 al mes, para minisúpers y cadenas.

La inversión inicial (unos $1,900) se recupera en el mes 2. Meta del año 1: 310 tiendas de paga.

## Pruebas
Más de 120 pruebas automáticas (funciones, facturas, seguridad, 12 dispositivos, app móvil, privacidad). Se
encontraron y corrigieron 19 fallas. Detalle en [docs/REPORTE_PRUEBAS.md](docs/REPORTE_PRUEBAS.md).

## Correrlo localmente
```bash
git clone https://github.com/Ernesto23lolxd/Prueba.git && cd Prueba/backend
pip install -r requirements.txt
echo "GEMINI_API_KEY=tu_clave" > .env
python -m uvicorn main:app --port 8000
```
Abrir http://localhost:8000/app. Sin `DATABASE_URL` usa SQLite local.

## Documentación
- [GUIA_DEL_CODIGO.md](docs/GUIA_DEL_CODIGO.md): cómo está armado el código.
- [API.md](docs/API.md): rutas del servidor.
- [SEGURIDAD.md](docs/SEGURIDAD.md): seguridad y privacidad.
- [REPORTE_PRUEBAS.md](docs/REPORTE_PRUEBAS.md): pruebas y fallas corregidas.
- [DIAGNOSTICO_FINAL.md](docs/DIAGNOSTICO_FINAL.md): estado final y pendientes.
- [DESPLIEGUE.md](docs/DESPLIEGUE.md): publicar con Supabase y Render.
- [MOVIL.md](docs/MOVIL.md): app instalable y APK.
- [PITCH_SPEECH.md](docs/PITCH_SPEECH.md): guion del pitch.

## Equipo
Braulio (backend), Jorge, Ernesto (diseño de la app y pitch), Sebas (diseño e identidad visual).
