# Diagnóstico final

Fecha: 20 de noviembre de 2026. Versión: rama `main`, publicada en https://stock-tienda.onrender.com.

Veredicto: lista para presentar y lanzar como piloto. Funciona de punta a punta en la nube, en celulares y en
computadoras, con seguridad, privacidad y documentos legales.

## Estado por área
- Funcionamiento: 32/32 pruebas de punta a punta.
- Facturas CFDI: 15/15.
- Ciberseguridad: 26/26.
- Privacidad: 0 fugas de datos sensibles (2/2).
- Legal: aviso y términos con aceptación obligatoria (3/3).
- Interfaz: 12/12 dispositivos.
- App móvil: PWA (4/4) y APK firmado.
- Emparejamiento de productos: 35/35.
- Nube: respuestas de 110 a 270 ms, 118 de 512 MB de memoria, 0 errores en registros.
- Repositorio: 0 secretos en el historial.

## Correcciones de la auditoría final
- Librería de PDF más ligera (`pypdf`): la memoria bajó de 351 a 118 MB.
- Versiones fijas en `requirements.txt`.
- Cabecera HSTS.
- Prueba del bloqueo del PIN más precisa.

En total se corrigieron 19 fallas (ver [REPORTE_PRUEBAS.md](REPORTE_PRUEBAS.md)).

## Pendientes para escalar
- Varias tiendas por servidor (id de tienda en cada tabla).
- Plan de pago de Render para que no se duerma.
- Respaldos de la base.
- Llave privada para el APK en Play Store.
- Revisión legal de los documentos.
- Probar el micrófono en un iPhone real.

## Día de la presentación
- Abrir la app 2 minutos antes.
- Aceptar aviso y términos y entrar con el PIN.
- Cambiar el PIN de demostración.
- Cargar la tienda de ejemplo y, al final, empezar de cero.
- Demo sugerida: voz, factura de ejemplo, "tengo $1,000" y deshacer.
