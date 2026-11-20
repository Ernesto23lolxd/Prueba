# Reporte de pruebas

Fecha: 20 de noviembre de 2026. Probado en servidor local (SQLite) y en la nube (Render y Supabase).

## Resultados
- `prueba_completa.py` (funciones de punta a punta): 32/32 local y nube.
- `prueba_auditoria.py` (seguridad): 26/26 local, 25/25 nube.
- `prueba_legal.py` (aviso y términos): 3/3.
- `prueba_privacidad.py` (limpieza de facturas): 2/2.
- `prueba_cfdi.py` (facturas): 15/15 local y nube.
- `prueba_emparejamiento.py` (buscador): 35/35.
- `prueba_interfaz.py` (12 dispositivos): 12/12 local y nube.
- `prueba_movil.py` (PWA): 4/4.

## Fallas corregidas (19)
1. Ventas simultáneas vendían de más: candado de escritura.
2. Se fusionaban productos distintos: nuevo buscador.
3. Notas de crédito y otros CFDI se sumaban: solo cuentan las de ingreso.
4. Los descuentos no se restaban del costo.
5. Facturas en dólares se guardaban como pesos.
6. Fletes y servicios entraban como mercancía.
7. El tutorial tapaba contenido en pantallas chicas.
8. Listas desbordadas con nombres largos.
9. Ids absurdos causaban error 500.
10. Se aceptaban nombres vacíos.
11. Conexiones de Postgres quedaban con transacción abierta.
12. El mismo PDF se sumaba dos veces: huella SHA-256 del archivo.
13. La IP se podía falsificar con `X-Forwarded-For`.
14. Los registros guardaban valores recibidos que podían incluir el PIN.
15. La portada pedía datos antes de entrar y el menú se desbordaba.
16. a 19. Ver [DIAGNOSTICO_FINAL.md](DIAGNOSTICO_FINAL.md).

## Pendientes
- Productos dados de alta por voz quedan con mínimo 0.
- En la nube, ráfagas de 25 peticiones por segundo pueden dar un 520 aislado.
- Render gratis se duerme tras 15 minutos.

## Repetir las pruebas
```bash
cd backend
RATE_LIMIT_POR_MINUTO=400 python -m uvicorn main:app --port 8000
python prueba_completa.py
python prueba_auditoria.py
python prueba_cfdi.py
python prueba_emparejamiento.py
python prueba_interfaz.py
```
