"""
Batería de facturas CFDI generadas aquí mismo y subidas a STOCK (usa IA para emparejar productos).

Uso:  python prueba_cfdi.py [url_base]      (por defecto http://127.0.0.1:8000)
Cada prueba arranca con la tienda de ejemplo recién cargada. Al final deja la demo cargada.
"""
import sys
import uuid as uuidlib

import fitz  # pymupdf: para generar la factura en PDF
import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
c = httpx.Client(base_url=BASE, timeout=180)
resultados = []
NS = {"4.0": "http://www.sat.gob.mx/cfd/4", "3.3": "http://www.sat.gob.mx/cfd/3"}


def prueba(nombre):
    def deco(f):
        try:
            c.post("/api/reset", json={"modo": "demo"})
            detalle = f() or "ok"
            resultados.append((True, nombre, detalle))
        except AssertionError as e:
            resultados.append((False, nombre, f"FALLA: {e}"))
        except Exception as e:  # noqa: BLE001
            resultados.append((False, nombre, f"ERROR: {type(e).__name__}: {e}"))
        return f
    return deco


def inv():
    return {p["nombre"]: p for p in c.get("/api/inventario").json()}


def cfdi(partidas, version="4.0", tipo="I", uuid=None, emisor="DISTRIBUIDORA DEL VALLE DEL GUADIANA",
         moneda="MXN", tipo_cambio=None, timbrado=True, encoding="UTF-8"):
    """partidas: lista de dicts con cantidad, clave_unidad, unidad, descripcion, valor_unitario y opcionales
    descuento y clave_prod."""
    conceptos, subtotal, descuentos = [], 0.0, 0.0
    for p in partidas:
        importe = round(p["cantidad"] * p["valor_unitario"], 2)
        subtotal += importe
        desc = p.get("descuento", 0)
        descuentos += desc
        attr_desc = f' Descuento="{desc:.2f}"' if desc else ""
        conceptos.append(
            f'<cfdi:Concepto ClaveProdServ="{p.get("clave_prod", "50202306")}" Cantidad="{p["cantidad"]}" '
            f'ClaveUnidad="{p["clave_unidad"]}" Unidad="{p["unidad"]}" Descripcion="{p["descripcion"]}" '
            f'ValorUnitario="{p["valor_unitario"]:.2f}" Importe="{importe:.2f}"{attr_desc} ObjetoImp="02"/>')
    total = subtotal - descuentos
    tc = f' TipoCambio="{tipo_cambio}"' if tipo_cambio else ""
    timbre = (f'<cfdi:Complemento><tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
              f'Version="1.1" UUID="{uuid or str(uuidlib.uuid4()).upper()}" FechaTimbrado="2026-11-19T10:00:00"/>'
              f'</cfdi:Complemento>') if timbrado else ""
    xml = (f'<?xml version="1.0" encoding="{encoding}"?>\n'
           f'<cfdi:Comprobante xmlns:cfdi="{NS[version]}" Version="{version}" Serie="A" Folio="1001" '
           f'Fecha="2026-11-19T09:30:00" FormaPago="03" SubTotal="{subtotal:.2f}" Descuento="{descuentos:.2f}" '
           f'Moneda="{moneda}"{tc} Total="{total:.2f}" TipoDeComprobante="{tipo}" Exportacion="01" MetodoPago="PUE" '
           f'LugarExpedicion="34000">'
           f'<cfdi:Emisor Rfc="DVG010101AB1" Nombre="{emisor}" RegimenFiscal="601"/>'
           f'<cfdi:Receptor Rfc="XAXX010101000" Nombre="TIENDITA DE PRUEBA" UsoCFDI="G01" '
           f'DomicilioFiscalReceptor="34000" RegimenFiscalReceptor="616"/>'
           f'<cfdi:Conceptos>{"".join(conceptos)}</cfdi:Conceptos>{timbre}</cfdi:Comprobante>')
    return xml.encode("utf-8" if encoding.upper() == "UTF-8" else "latin-1")


def subir_xml(xml, nombre="factura.xml"):
    return c.post("/api/cfdi", files={"archivo": (nombre, xml, "text/xml")})


def P(cantidad, clave_unidad, unidad, descripcion, valor_unitario, **extra):
    return {"cantidad": cantidad, "clave_unidad": clave_unidad, "unidad": unidad, "descripcion": descripcion,
            "valor_unitario": valor_unitario, **extra}


def subio(antes, despues, nombre, esperado, tolerancia=0.01):
    real = despues[nombre]["cantidad"] - antes[nombre]["cantidad"]
    assert abs(real - esperado) <= tolerancia, f"{nombre}: subió {real:g}, se esperaba {esperado:g}"


def sin_duplicados(antes, despues, permitidos=()):
    nuevos = sorted(set(despues) - set(antes) - set(permitidos))
    assert not nuevos, f"creó productos duplicados en vez de emparejar: {nuevos}"


# ------------------------------------------------------------------ Emparejamiento (lo que pidió el profe)
@prueba("C1. CFDI 4.0 con descripciones de proveedor ('CIEL 1000', 'COCA COLA 600ML PET C/24')")
def _():
    antes = inv()
    r = subir_xml(cfdi([
        P(1, "XBX", "CAJA", "CIEL 1000 ML C/12", 132.00),
        P(2, "XBX", "CAJA", "COCA COLA 600ML PET C/24", 396.00),
        P(1, "XPK", "PAQUETE", "LALA ENTERA 1LT C/12", 276.00),
        P(1, "XBX", "CAJA", "SABRITAS SAL 45GR C/20", 300.00),
    ]))
    assert r.status_code == 200, r.text[:300]
    despues = inv()
    sin_duplicados(antes, despues)
    subio(antes, despues, "Agua Ciel 1 L", 12)
    subio(antes, despues, "Coca-Cola 600 ml", 48)
    subio(antes, despues, "Leche Lala 1 L", 12)
    subio(antes, despues, "Sabritas sal 45 g", 20)
    return "Ciel +12, Coca +48, Lala +12, Sabritas +20; sin duplicados — " + r.json()["respuesta"][:90]


@prueba("C2. CFDI 3.3 (versión anterior) con abreviaturas y kilos")
def _():
    antes = inv()
    r = subir_xml(cfdi([
        P(2, "XSA", "BULTO", "FRIJOL PINTO SACO 25 KG", 650.00),
        P(1, "XBX", "CAJA", "ACEITE 123 1LT C/12", 492.00),
        P(3, "H87", "PIEZA", "PAN BCO BIMBO GDE", 42.00),
    ], version="3.3"))
    assert r.status_code == 200, r.text[:300]
    despues = inv()
    sin_duplicados(antes, despues)
    subio(antes, despues, "Frijol pinto", 50)
    subio(antes, despues, "Aceite 1-2-3 1 L", 12)
    subio(antes, despues, "Pan Bimbo grande", 3)
    return "Frijol +50 kg, Aceite +12, Pan +3"


@prueba("C3. Fletes y servicios (por clave de unidad y por clave de producto SAT) no entran al inventario")
def _():
    antes = inv()
    r = subir_xml(cfdi([
        P(1, "XBX", "CAJA", "COCA COLA 600ML PET C/24", 396.00),
        P(1, "E48", "SERVICIO", "FLETE LOCAL DURANGO", 150.00, clave_prod="78101802"),
        P(1, "H87", "PIEZA", "MANIOBRA DE DESCARGA", 80.00, clave_prod="78141500"),
    ]))
    assert r.status_code == 200, r.text[:300]
    despues = inv()
    sin_duplicados(antes, despues)
    subio(antes, despues, "Coca-Cola 600 ml", 24)
    assert "concepto" in r.json()["respuesta"].lower() or "servicio" in r.json()["respuesta"].lower()
    return "solo Coca +24; flete y maniobra fuera"


@prueba("C4. Factura de puro servicio → no toca nada")
def _():
    antes = inv()
    r = subir_xml(cfdi([P(1, "E48", "SERVICIO", "RENTA DE REFRIGERADOR", 500.00, clave_prod="80131500")]))
    assert r.status_code == 200 and r.json().get("factura", {}).get("solo_servicios"), r.text[:200]
    assert inv() == antes
    return "inventario intacto"


@prueba("C5. Notas de crédito, pagos, traslados y nómina se rechazan con mensaje claro")
def _():
    antes = inv()
    msgs = []
    for tipo in ("E", "P", "T", "N"):
        r = subir_xml(cfdi([P(1, "XBX", "CAJA", "COCA COLA 600ML PET C/24", 396.00)], tipo=tipo))
        assert r.status_code == 400, (tipo, r.status_code, r.text[:200])
        msgs.append(f"{tipo}: {r.json()['detail'][:45]}…")
    assert inv() == antes, "cambió el inventario"
    return " | ".join(msgs)


@prueba("C6. Descuento en la partida: el costo real baja y no hay alerta falsa de inflación")
def _():
    antes = inv()
    # 24 Cocas a 16.50 = 396, con 10 % de descuento → costo real 14.85 por pieza (antes 16.50)
    r = subir_xml(cfdi([P(1, "XBX", "CAJA", "COCA COLA 600ML PET C/24", 396.00, descuento=39.60)]))
    assert r.status_code == 200, r.text[:300]
    despues = inv()
    subio(antes, despues, "Coca-Cola 600 ml", 24)
    costo = despues["Coca-Cola 600 ml"]["costo_compra"]
    assert abs(costo - 14.85) < 0.02, f"costo {costo}, se esperaba 14.85"
    assert not r.json().get("alertas_precio"), r.json().get("alertas_precio")
    return f"costo por pieza {costo} y sin alerta"


@prueba("C7. Subida de precio del proveedor → escudo anti-inflación con precio sugerido")
def _():
    r = subir_xml(cfdi([P(1, "XBX", "CAJA", "COCA COLA 600ML PET C/24", 480.00)]))  # 20 por pieza (antes 16.50)
    assert r.status_code == 200, r.text[:300]
    alertas = r.json().get("alertas_precio") or []
    assert alertas and alertas[0]["producto"] == "Coca-Cola 600 ml", alertas
    a = alertas[0]
    assert a["costo_nuevo"] == 20 and a["subida_pct"] > 20 and a["precio_sugerido"] == 25, a
    return a["mensaje"][:110]


@prueba("C8. Factura en dólares con tipo de cambio → costos en pesos")
def _():
    r = subir_xml(cfdi([P(1, "XBX", "CAJA", "COCA COLA 600ML PET C/24", 21.60)], moneda="USD", tipo_cambio="18.50"))
    assert r.status_code == 200, r.text[:300]
    costo = inv()["Coca-Cola 600 ml"]["costo_compra"]
    assert abs(costo - 16.65) < 0.05, f"costo {costo} (21.60 USD × 18.50 / 24 = 16.65 MXN)"
    assert abs(r.json()["factura"]["total"] - 399.6) < 0.1, r.json()["factura"]
    return f"costo {costo} MXN por pieza"


@prueba("C9. Misma factura dos veces → 409 y sin duplicar; sin timbre también se detecta")
def _():
    folio = str(uuidlib.uuid4()).upper()
    xml = cfdi([P(1, "XBX", "CAJA", "COCA COLA 600ML PET C/24", 396.00)], uuid=folio)
    assert subir_xml(xml).status_code == 200
    despues1 = inv()
    r = subir_xml(xml)
    assert r.status_code == 409, r.status_code
    assert inv() == despues1
    sin_timbre = cfdi([P(1, "XBX", "CAJA", "CIEL 1000 ML C/12", 132.00)], timbrado=False)
    assert subir_xml(sin_timbre).status_code == 200
    assert subir_xml(sin_timbre).status_code == 409
    return "duplicados bloqueados (con y sin timbre)"


@prueba("C10. Codificación ISO-8859-1, BOM y acentos en descripciones")
def _():
    antes = inv()
    xml = cfdi([P(1, "XBX", "CAJA", "JABÓN ZOTE ROSA 400G C/25", 400.00)], encoding="ISO-8859-1")
    r = subir_xml(xml)
    assert r.status_code == 200, r.text[:300]
    subio(antes, inv(), "Jabón Zote", 25)
    bom = b"\xef\xbb\xbf" + cfdi([P(1, "XBX", "CAJA", "MARUCHAN CAMARON C/12", 144.00)])
    r = subir_xml(bom)
    assert r.status_code == 200, r.text[:300]
    subio(antes, inv(), "Maruchan", 12)
    return "Latin-1 y BOM leídos; Zote +25, Maruchan +12"


@prueba("C11. Producto nuevo que la tienda no tenía → se da de alta con su costo, sin alerta")
def _():
    antes = inv()
    r = subir_xml(cfdi([P(2, "XBX", "CAJA", "GANSITO MARINELA C/8", 160.00)]))
    assert r.status_code == 200, r.text[:300]
    despues = inv()
    nuevos = set(despues) - set(antes)
    assert len(nuevos) == 1, nuevos
    nuevo = despues[nuevos.pop()]
    assert nuevo["cantidad"] == 16 and abs(nuevo["costo_compra"] - 20) < 0.01, nuevo
    assert not r.json().get("alertas_precio")
    return f"alta de '{nuevo['nombre']}' con 16 piezas a $20 de costo"


@prueba("C12. Factura grande de 25 partidas con cantidades decimales")
def _():
    partidas = [P(1.5, "KGM", "KILO", "JAMON DE PAVO FUD", 120.00), P(2.25, "KGM", "KILO", "AZUCAR ESTANDAR", 22.00)]
    for k in range(23):
        partidas.append(P(1, "H87", "PIEZA", f"ARTICULO DE PRUEBA NUMERO {k + 1}", 10.00 + k))
    antes = inv()
    r = subir_xml(cfdi(partidas))
    assert r.status_code == 200, r.text[:300]
    despues = inv()
    subio(antes, despues, "Jamón de pavo", 1.5)
    subio(antes, despues, "Azúcar", 2.25)
    nuevos = set(despues) - set(antes)
    assert len(nuevos) == 23, f"se esperaban 23 altas y hubo {len(nuevos)}"
    return "25 partidas: 2 emparejadas con decimales y 23 altas"


@prueba("C13. Deshacer la factura regresa existencias y costos exactos")
def _():
    antes = inv()
    r = subir_xml(cfdi([P(2, "XBX", "CAJA", "COCA COLA 600ML PET C/24", 480.00),
                        P(1, "XBX", "CAJA", "GANSITO MARINELA C/8", 160.00)]))
    assert r.status_code == 200
    lote = r.json()["lote_id"]
    d = c.post(f"/api/lotes/{lote}/deshacer")
    assert d.status_code == 200, d.text[:200]
    despues = inv()
    assert set(despues) == set(antes), "quedó el producto nuevo"
    for n in antes:
        assert despues[n]["cantidad"] == antes[n]["cantidad"] and despues[n]["costo_compra"] == antes[n]["costo_compra"], n
    return "todo como estaba antes de la factura"


@prueba("C14. Factura en PDF (generada aquí) se lee con IA y suma")
def _():
    doc = fitz.open()
    pag = doc.new_page()
    texto = ("DISTRIBUIDORA DEL VALLE DEL GUADIANA SA DE CV   RFC DVG010101AB1\n"
             "FACTURA CFDI 4.0   Folio fiscal: 7A1B2C3D-4E5F-4A6B-8C7D-PDF000000001\n"
             "Fecha: 19/11/2026    Forma de pago: 03 Transferencia\n\n"
             "Cant  Unidad  Descripción                      P. Unitario   Importe\n"
             "2     CAJA    COCA COLA 600ML PET C/24          396.00        792.00\n"
             "1     CAJA    CIEL 1000 ML C/12                 132.00        132.00\n\n"
             "Subtotal 924.00     Total 924.00")
    pag.insert_text((40, 60), texto, fontsize=10)
    pdf = doc.tobytes()
    antes = inv()
    r = c.post("/api/cfdi", files={"archivo": ("factura.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text[:300]
    despues = inv()
    sin_duplicados(antes, despues)
    subio(antes, despues, "Coca-Cola 600 ml", 48)
    subio(antes, despues, "Agua Ciel 1 L", 12)
    assert c.post("/api/cfdi", files={"archivo": ("otra.pdf", pdf, "application/pdf")}).status_code == 409
    return "PDF: Coca +48, Ciel +12; repetido → 409"


@prueba("C15. Tienda en ceros + primera factura → arma el inventario desde cero")
def _():
    c.post("/api/reset", json={"modo": "vacio"})
    r = subir_xml(cfdi([P(2, "XBX", "CAJA", "COCA COLA 600ML PET C/24", 396.00),
                        P(1, "XSA", "BULTO", "FRIJOL PINTO SACO 25 KG", 650.00)]))
    assert r.status_code == 200, r.text[:300]
    i = inv()
    assert len(i) == 2, i.keys()
    cantidades = sorted(p["cantidad"] for p in i.values())
    assert cantidades == [25, 48], cantidades
    t = c.get("/api/tablero")
    assert t.status_code == 200
    return "2 productos dados de alta: " + ", ".join(f"{n} ({p['cantidad']:g})" for n, p in i.items())


c.post("/api/reset", json={"modo": "demo"})
print(f"\nBatería de facturas CFDI contra {BASE}\n")
for ok, nombre, detalle in resultados:
    print(f"{'✅' if ok else '❌'} {nombre}\n     {detalle}")
fallas = sum(not ok for ok, *_ in resultados)
print(f"\n{len(resultados) - fallas}/{len(resultados)} pruebas pasaron")
sys.exit(1 if fallas else 0)
