# Guía del código

## Idea general
La app manda lo que dice el tendero al servidor. El servidor le pide a Gemini que lo interprete, valida la respuesta,
actualiza el inventario y contesta. Regla: el modelo propone y Python calcula y valida. Las cuentas de dinero nunca
las hace el modelo.

## Carpetas
- `backend/main.py`: rutas `/api`, inventario, facturas, predicción.
- `backend/basedatos.py`: SQLite local o Postgres en la nube.
- `backend/seguridad.py`: archivos, límites, IP real, cabeceras.
- `backend/acceso.py`: PIN y sesiones.
- `backend/privacidad.py`: limpieza de datos personales de las facturas.
- `backend/cfdi.py`: lectura segura de facturas XML.
- `backend/importar.py`: lectura de Excel y CSV.
- `backend/prueba_*.py`: pruebas.
- `app/`: interfaz (HTML, Tailwind, JavaScript), portada, documentos legales y PWA.
- `android/`: APK (Trusted Web Activity).
- `render.yaml`: despliegue en Render.

## Flujo de una venta por voz
1. La app graba el audio y lo envía a `POST /api/voz`.
2. El servidor revisa la sesión del PIN y el límite por IP.
3. Valida que sea audio real y que no pase de 10 MB.
4. Envía a Gemini las instrucciones, el inventario y el audio.
5. Gemini responde un JSON con acciones.
6. `validar_salida_ia()` descarta lo inválido.
7. `aplicar_acciones()` busca el producto y lo descuenta con candado.
8. Todo queda en un lote que se puede deshacer.

## Tablas
- `productos`: nombre, unidad, cantidad, mínimo, precio, categoría y costo.
- `movimientos`: cada cambio con su valor anterior y su lote.
- `lotes`: cada acción completa.
- `cfdi_procesados`: facturas ya sumadas, con huella para evitar duplicados.
- `ajustes`: PIN, sesiones y aceptación legal.

## Facturas
Se calcula la huella del archivo para evitar duplicados. Del XML se leen partidas, descuentos y moneda; solo las
facturas de ingreso suman. Se separan los servicios, se envían al modelo solo los datos mínimos, y Python calcula el
costo real por pieza y avisa si subió el precio.

## Correrlo
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```
No usar `--reload` dentro de OneDrive.

## Pruebas
- `prueba_completa.py`: 32 de punta a punta.
- `prueba_auditoria.py`: 26 de seguridad.
- `prueba_cfdi.py`: 15 facturas.
- `prueba_interfaz.py`: 12 dispositivos.
- `prueba_movil.py`: app instalable.
- `prueba_legal.py`: aceptación del aviso y términos.
- `prueba_privacidad.py`: limpieza de facturas (sin servidor).
- `prueba_emparejamiento.py`: buscador de productos (sin servidor).

Las pruebas con servidor usan el PIN de `STOCK_PIN` y aceptan el aviso legal; no correrlas contra una tienda real.
