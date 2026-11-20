"""
Prueba completa de STOCK (correr con el servidor encendido):

    cd backend
    python prueba_completa.py                # contra http://localhost:8000
    python prueba_completa.py http://IP:8000 # contra otra máquina

Prueba: página y archivos, inventario, predicción, lista de compras, WhatsApp,
voz con audio real, texto con Gemini, protecciones, importación de Excel/CSV y reinicio.
Al final deja los datos de demo como al principio.
"""
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
DEMO = Path(__file__).resolve().parent.parent / "demo"
resultados = []


def pedir(metodo, ruta, json_body=None, archivos=None, campos=None, timeout=90):
    headers, datos = {}, None
    if json_body is not None:
        datos = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif archivos or campos:
        frontera = uuid.uuid4().hex
        partes = []
        for nombre, valor in (campos or {}).items():
            partes.append(f'--{frontera}\r\nContent-Disposition: form-data; name="{nombre}"\r\n\r\n{valor}\r\n'.encode())
        for nombre, (archivo, contenido, tipo) in (archivos or {}).items():
            partes.append(
                f'--{frontera}\r\nContent-Disposition: form-data; name="{nombre}"; filename="{archivo}"\r\n'
                f"Content-Type: {tipo}\r\n\r\n".encode() + contenido + b"\r\n"
            )
        datos = b"".join(partes) + f"--{frontera}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={frontera}"
    req = urllib.request.Request(BASE + ruta, data=datos, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cuerpo = r.read()
            return r.status, (json.loads(cuerpo) if "json" in r.headers.get("Content-Type", "") else cuerpo.decode())
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode()
        try:
            return e.code, json.loads(cuerpo)
        except json.JSONDecodeError:
            return e.code, cuerpo


def prueba(nombre):
    def decorador(fn):
        t = time.time()
        try:
            detalle = fn() or ""
            resultados.append((True, nombre, f"{detalle} ({time.time() - t:.1f}s)"))
        except AssertionError as e:
            resultados.append((False, nombre, str(e)))
        except Exception as e:  # noqa: BLE001
            resultados.append((False, nombre, f"{type(e).__name__}: {e}"))
        return fn
    return decorador


def inv():
    return {p["nombre"]: p for p in pedir("GET", "/api/inventario")[1]}


def texto(frase):
    codigo, d = pedir("POST", "/api/texto", {"texto": frase})
    assert codigo == 200, f"HTTP {codigo}: {d}"
    return d


# ------------------------------------------------------------------ Pruebas
pedir("POST", "/api/reset")


@prueba("1. La página y sus archivos cargan")
def _():
    for ruta in ["/", "/app", "/clasico", "/static/app.js", "/static/styles.css"]:
        codigo, _ = pedir("GET", ruta)
        assert codigo == 200, f"{ruta} -> HTTP {codigo}"
    return "portada, app, clásico, app.js, styles.css"


@prueba("2. Inventario de demo (20 productos)")
def _():
    i = inv()
    assert len(i) == 20, f"hay {len(i)} productos"
    return f"{len(i)} productos"


@prueba("3. Predicción: cuándo se acaba y cuánto comprar")
def _():
    _, p = pedir("GET", "/api/prediccion")
    huevo = next(x for x in p if x["nombre"] == "Huevo")
    assert huevo["venta_diaria"] > 0 and huevo["se_acaba_texto"], huevo
    assert p[0]["urgencia"] == "alta", "lo urgente debe ir primero"
    return f"huevo: {huevo['venta_diaria']}/día, se acaba {huevo['se_acaba_texto']}"


@prueba("4. Lista de compras + enlace de WhatsApp")
def _():
    _, l = pedir("GET", "/api/lista-compras")
    assert l["items"] and l["whatsapp_url"].startswith("https://wa.me/?text="), l
    tortillas = next((x for x in l["items"] if x["nombre"] == "Tortillas"), None)
    assert not tortillas or tortillas["cantidad"] < 10, "tortilla perecedera: compra de pocos días"
    return f"{len(l['items'])} productos, ${l['total_estimado']:,.0f}"


@prueba("5. Texto: venta de varios productos en una frase")
def _():
    antes = inv()
    d = texto("vendí 3 cocas y 2 sabritas")
    despues = inv()
    assert despues["Coca-Cola 600 ml"]["cantidad"] == antes["Coca-Cola 600 ml"]["cantidad"] - 3
    assert despues["Sabritas sal 45 g"]["cantidad"] == antes["Sabritas sal 45 g"]["cantidad"] - 2
    return f"“{d['respuesta'][:60]}…”"


@prueba("6. Texto: entrada de mercancía")
def _():
    antes = inv()["Frijol pinto"]["cantidad"]
    texto("llegaron 10 kilos de frijol")
    assert inv()["Frijol pinto"]["cantidad"] == antes + 10
    return "frijol +10 kg"


@prueba("7. Texto: pregunta de predicción")
def _():
    d = texto("¿cuándo se me acaba el huevo?")
    assert not d["acciones"], "una pregunta no debe cambiar el inventario"
    assert d["respuesta"], "sin respuesta"
    return f"“{d['respuesta'][:70]}…”"


@prueba("8. Texto: 'mándale la lista al proveedor' da botón de WhatsApp")
def _():
    d = texto("mándale la lista al proveedor por WhatsApp")
    assert d.get("whatsapp_url"), "no regresó whatsapp_url"
    assert "mandé" not in d["respuesta"].lower(), f"no debe decir que ya lo envió: {d['respuesta']}"
    return "botón presente"


@prueba("9. Protección: no vender más de lo que hay")
def _():
    antes = inv()["Coca-Cola 600 ml"]["cantidad"]
    d = texto("vendí 500 cocas")
    assert inv()["Coca-Cola 600 ml"]["cantidad"] == antes, "cambió el inventario"
    assert any(not a["ok"] for a in d["acciones"]) or not d["acciones"], d
    return "rechazado"


@prueba("10. Texto: cambio de precio")
def _():
    texto("súbele el precio a la coca a 23")
    assert inv()["Coca-Cola 600 ml"]["precio"] == 23
    return "Coca a $23"


@prueba("11. Voz: audio real 'vendí tres cocas y dos sabritas'")
def _():
    wav = DEMO / "voz_venta.wav"
    assert wav.exists(), "falta demo/voz_venta.wav"
    antes = inv()["Coca-Cola 600 ml"]["cantidad"]
    codigo, d = pedir("POST", "/api/voz", archivos={"audio": ("voz.wav", wav.read_bytes(), "audio/wav")})
    assert codigo == 200, f"HTTP {codigo}: {d}"
    assert inv()["Coca-Cola 600 ml"]["cantidad"] == antes - 3, f"entendió: {d.get('transcripcion')}"
    return f"entendió “{d['transcripcion']}”"


@prueba("12. Voz: audio real '¿cuándo se me acaba el huevo?'")
def _():
    wav = DEMO / "voz_prediccion.wav"
    codigo, d = pedir("POST", "/api/voz", archivos={"audio": ("voz.wav", wav.read_bytes(), "audio/wav")})
    assert codigo == 200 and d["respuesta"], d
    return f"“{d['respuesta'][:60]}…”"


@prueba("13. Excel con título y fila TOTAL: vista previa y guardado")
def _():
    xlsx = DEMO / "inventario_ejemplo_tienda.xlsx"
    tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    archivos = {"archivo": (xlsx.name, xlsx.read_bytes(), tipo)}
    _, v = pedir("POST", "/api/importar", archivos=archivos, campos={"confirmar": "false"})
    assert len(v["productos"]) == 10, f"leyó {len(v['productos'])} productos"
    assert "Queso menonita" not in inv(), "la vista previa no debe guardar"
    _, g = pedir("POST", "/api/importar", archivos=archivos, campos={"confirmar": "true"})
    assert g["guardado"] and "Queso menonita" in inv()
    return f"{g['nuevos']} nuevos, {g['actualizados']} actualizados, método: {g['metodo']}"


@prueba("14. CSV con columnas informales ('Lo que vendo', 'Cuántos me quedan')")
def _():
    csvf = DEMO / "inventario_raro.csv"
    _, v = pedir("POST", "/api/importar", archivos={"archivo": (csvf.name, csvf.read_bytes(), "text/csv")},
                 campos={"confirmar": "false"})
    assert v["columnas"].get("nombre") == "Lo que vendo" and v["columnas"].get("cantidad") == "Cuántos me quedan", v["columnas"]
    return f"método: {v['metodo']}"


@prueba("15. Archivo inválido da error claro")
def _():
    codigo, d = pedir("POST", "/api/importar", archivos={"archivo": ("x.pdf", b"%PDF", "application/pdf")})
    assert codigo == 400 and "detail" in d, (codigo, d)
    return d["detail"]


@prueba("16. Historial de movimientos")
def _():
    _, m = pedir("GET", "/api/movimientos?limite=5")
    assert len(m) == 5 and m[0]["fecha"], m
    return f"último: {m[0]['tipo']} {m[0]['nombre']}"


BACKEND = Path(__file__).resolve().parent


@prueba("17. Factura XML (CFDI): convierte cajas a piezas y suma al inventario")
def _():
    pedir("POST", "/api/reset")
    # Costo anterior de la Coca más bajo, para comprobar el aviso de "te llegó más caro"
    csv_costo = "Producto,Existencia,Costo\nCoca-Cola 600 ml,30,15\n".encode()
    pedir("POST", "/api/importar", archivos={"archivo": ("costos.csv", csv_costo, "text/csv")}, campos={"confirmar": "true"})
    antes = inv()
    xml = (BACKEND / "demo_cfdi.xml").read_bytes()
    codigo, d = pedir("POST", "/api/cfdi", archivos={"archivo": ("demo_cfdi.xml", xml, "text/xml")}, timeout=120)
    assert codigo == 200, (codigo, d)
    despues = inv()
    esperado = {"Coca-Cola 600 ml": 72, "Leche Lala 1 L": 12, "Frijol pinto": 10, "Pan Bimbo grande": 8}
    for nombre, suma in esperado.items():
        real = despues[nombre]["cantidad"] - antes[nombre]["cantidad"]
        assert real == suma, f"{nombre}: sumó {real}, esperaba {suma} (cajas → piezas)"
    assert "más caro" in d["respuesta"], f"falta aviso de precio: {d['respuesta']}"
    assert "efectivo" in d["respuesta"], f"falta tip de efectivo: {d['respuesta']}"
    for palabra in ["IVA", "ISR", "RESICO", "póliza", "acreditable"]:
        assert palabra.lower() not in d["respuesta"].lower(), f"lenguaje fiscal en la respuesta: {palabra}"
    return "72 Cocas, 12 leches, 10 kg frijol, 8 panes + avisos amables"


@prueba("18. Misma factura otra vez → 409 sin duplicar inventario")
def _():
    antes = inv()["Coca-Cola 600 ml"]["cantidad"]
    codigo, d = pedir("POST", "/api/cfdi/demo")
    assert codigo == 409 and "ya la subiste" in d["detail"], (codigo, d)
    assert inv()["Coca-Cola 600 ml"]["cantidad"] == antes, "duplicó el inventario"
    return d["detail"]


@prueba("19. Factura en PDF (lectura con IA)")
def _():
    pdf = (DEMO / "factura_ejemplo.pdf").read_bytes()
    antes = inv()
    codigo, d = pedir("POST", "/api/cfdi", archivos={"archivo": ("factura_ejemplo.pdf", pdf, "application/pdf")}, timeout=120)
    assert codigo == 200, (codigo, d)
    despues = inv()
    sab = despues["Sabritas sal 45 g"]["cantidad"] - antes["Sabritas sal 45 g"]["cantidad"]
    atun = despues["Atún Dolores"]["cantidad"] - antes["Atún Dolores"]["cantidad"]
    huevo = despues["Huevo"]["cantidad"] - antes["Huevo"]["cantidad"]
    assert sab == 24 and atun == 24, f"Sabritas +{sab} (esp. 24), Atún +{atun} (esp. 24)"
    assert 2.5 <= huevo <= 5, f"Huevo +{huevo} kg (2 charolas de 30 ≈ 3.6 kg)"
    codigo2, _ = pedir("POST", "/api/cfdi", archivos={"archivo": ("factura_ejemplo.pdf", pdf, "application/pdf")}, timeout=120)
    assert codigo2 == 409, f"el PDF repetido debió dar 409 y dio {codigo2}"
    return f"Sabritas +{sab:g}, Atún +{atun:g}, Huevo +{huevo:g} kg; repetido → 409"


@prueba("20. Archivo que no es factura → error claro")
def _():
    codigo, d = pedir("POST", "/api/cfdi", archivos={"archivo": ("nota.xml", b"<hola/>", "text/xml")})
    assert codigo == 400 and "factura" in d["detail"].lower(), (codigo, d)
    return d["detail"]


@prueba("21. Resumen del mes")
def _():
    codigo, m = pedir("GET", "/api/resumen-mes")
    assert codigo == 200 and m["surtido"]["facturas"] == 2, m.get("surtido")
    assert m["vendido"]["monto"] > 0 and m["mas_vendidos"] and "monto" in m["dinero_parado"], m
    return (f"{m['mes']}: vendido ${m['vendido']['monto']:,.0f}, surtido ${m['surtido']['monto']:,.0f} "
            f"({m['surtido']['facturas']} facturas), parado ${m['dinero_parado']['monto']:,.0f}")


@prueba("22. Resumen del mes en CSV descargable")
def _():
    codigo, texto = pedir("GET", "/api/resumen-mes/csv")
    assert codigo == 200 and isinstance(texto, str), codigo
    assert "FACTURAS DE PROVEEDOR CARGADAS" in texto and "DISTRIBUIDORA ABARROTERA DEL GUADIANA" in texto, texto[:300]
    return f"{texto.count(chr(10))} renglones"


@prueba("23. Reinicio de datos de demo (también borra facturas)")
def _():
    pedir("POST", "/api/reset")
    i = inv()
    assert len(i) == 20 and "Queso menonita" not in i
    _, m = pedir("GET", "/api/resumen-mes")
    assert m["surtido"]["facturas"] == 0, "quedaron facturas tras el reinicio"
    codigo, _ = pedir("POST", "/api/cfdi/demo")
    assert codigo == 200, "tras reiniciar, la factura demo debe poder subirse otra vez"
    pedir("POST", "/api/reset")
    return "20 productos y 0 facturas"


# ------------------------------------------------------------------ Reporte
print(f"\nPrueba completa de STOCK contra {BASE}\n")
for ok, nombre, detalle in resultados:
    print(f"{'✅' if ok else '❌'} {nombre}\n     {detalle}")
fallas = sum(not ok for ok, *_ in resultados)
print(f"\n{len(resultados) - fallas}/{len(resultados)} pruebas pasaron")
sys.exit(1 if fallas else 0)
