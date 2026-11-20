"""
Prueba del escudo de privacidad de facturas (sin servidor ni IA).

Uso:  python prueba_privacidad.py
Comprueba que a la IA NO le llega ningún dato sensible (RFC, CURP, nombres, domicilio, correo, teléfono, folio,
cuenta bancaria, sello, certificado, cadena original) y que SÍ le llega todo lo necesario para inventariar.
"""
import sys

import cfdi
import privacidad

resultados = []


def prueba(nombre, f):
    try:
        resultados.append((True, nombre, f() or "ok"))
    except AssertionError as e:
        resultados.append((False, nombre, f"FALLA: {e}"))


SENSIBLES = ["DVG010101AB1", "LUPM850101HD3", "LUPM850101MDGPRR09", "ventas@valleguadiana.mx", "811 2233",
             "123 4567", "Calle 5 de Febrero", "34000", "5E2A1C3B-9F4D-4A7E-8B21-0D0A20260001", "012180001234567891",
             "MIIBIjAN", "30001000000500003416", "Abarrotes Lupita", "Juan Pérez", "SAT970701NN3",
             "DISTRIBUIDORA DEL VALLE"]

TEXTO_PDF = """DISTRIBUIDORA DEL VALLE DEL GUADIANA SA DE CV
RFC: DVG010101AB1   Régimen Fiscal: 601 General de Ley
Domicilio: Calle 5 de Febrero 123 Col. Centro, C.P. 34000 Durango, Dgo.
Tel. (618) 811 2233   correo: ventas@valleguadiana.mx
Receptor: Abarrotes Lupita   RFC: LUPM850101HD3   CURP: LUPM850101MDGPRR09
Uso CFDI: G01   Lugar de expedición: 34000
Folio fiscal: 5E2A1C3B-9F4D-4A7E-8B21-0D0A20260001
Fecha: 19/11/2026    Forma de pago: 03 Transferencia
Cuenta CLABE 012180001234567891
Cant  Unidad  Descripción                      P. Unitario   Importe
2     CAJA    COCA COLA 600ML PET C/24          396.00        792.00
1     CAJA    CIEL 1000 ML C/12                 132.00        132.00
1     KILO    QUESO MENONITA (pedido de Juan Pérez, tel 618 123 4567)   140.50   140.50
3     PZA     JABON ZOTE 400G ventas@valleguadiana.mx DVG010101AB1         22.00     66.00
Subtotal 1,130.50     Total 1,130.50
Sello digital del CFDI: MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLez
No. de serie del certificado: 30001000000500003416
||1.1|5E2A1C3B-9F4D-4A7E-8B21-0D0A20260001|2026-11-19T10:00:00|SAT970701NN3|abc==||"""

XML = """<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Version="4.0" Total="1130.50" FormaPago="03"
  TipoDeComprobante="I" LugarExpedicion="34000" NoCertificado="30001000000500003416" Sello="MIIBIjANBgkqhkiG9w0BAQEFAAOC"
  Certificado="MIIFuzCCA6OgAwIBAgIUMzAwMDEwMDAwMDA1MDAwMDM0MTYwDQ">
 <cfdi:Emisor Rfc="DVG010101AB1" Nombre="DISTRIBUIDORA DEL VALLE DEL GUADIANA" RegimenFiscal="601"/>
 <cfdi:Receptor Rfc="LUPM850101HD3" Nombre="Abarrotes Lupita" DomicilioFiscalReceptor="34000" UsoCFDI="G01"
   RegimenFiscalReceptor="612"/>
 <cfdi:Conceptos>
  <cfdi:Concepto ClaveProdServ="50202306" Cantidad="2" ClaveUnidad="XBX" Unidad="CAJA"
    Descripcion="COCA COLA 600ML PET C/24" ValorUnitario="396.00" Importe="792.00"/>
  <cfdi:Concepto ClaveProdServ="50202301" Cantidad="1" ClaveUnidad="XBX" Unidad="CAJA"
    Descripcion="CIEL 1000 ML C/12 entregar a Juan Perez tel 618 123 4567 ventas@valleguadiana.mx" ValorUnitario="132.00"
    Importe="132.00"/>
 </cfdi:Conceptos>
 <cfdi:Complemento><tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
   UUID="5E2A1C3B-9F4D-4A7E-8B21-0D0A20260001" SelloSAT="MIIBIjANBgkq" NoCertificadoSAT="30001000000500003416"/>
 </cfdi:Complemento>
</cfdi:Comprobante>""".encode()


def pdf():
    quitado = set()
    a_la_ia = privacidad.texto_minimo_pdf(TEXTO_PDF, quitado)
    fugas = [x for x in SENSIBLES if x in a_la_ia]
    assert not fugas, f"llegarían a la IA: {fugas}"
    for necesario in ("COCA COLA 600ML PET C/24", "CIEL 1000 ML C/12", "QUESO MENONITA", "JABON ZOTE 400G",
                      "396.00", "140.50", "66.00"):
        assert necesario in a_la_ia, f"se perdió un dato necesario para inventariar: {necesario}"
    local = privacidad.datos_locales_pdf(TEXTO_PDF)
    assert local["uuid"] == "5E2A1C3B-9F4D-4A7E-8B21-0D0A20260001" and local["total"] == 1130.5
    assert local["forma_pago"] == "03" and local["proveedor"].startswith("DISTRIBUIDORA")
    return f"0 fugas; 4 productos y precios conservados; protegido: {', '.join(privacidad.resumen(quitado, 4)['protegido'])}"


def xml():
    f = cfdi.leer_cfdi(XML)
    quitado = set(f["sensibles"])
    a_la_ia = privacidad.partidas_minimas(f["conceptos"], quitado)
    fugas = [x for x in SENSIBLES + ["Juan Perez", "Lupita", "601", "G01"] if x in a_la_ia]
    assert not fugas, f"llegarían a la IA: {fugas}"
    for necesario in ("COCA COLA 600ML PET C/24", "CIEL 1000 ML C/12", "CAJA", "396.00", "132.00"):
        assert necesario in a_la_ia, f"se perdió: {necesario}"
    # lo fiscal sigue disponible SOLO en el servidor (para duplicados y el resumen del mes)
    assert f["uuid"] == "5E2A1C3B-9F4D-4A7E-8B21-0D0A20260001" and f["rfc"] == "DVG010101AB1"
    esperado = {"RFC", "nombres", "domicilio fiscal", "folio fiscal", "sellos y certificados", "datos fiscales"}
    assert esperado <= quitado, esperado - quitado
    return "a la IA solo llegan cantidad, unidad, descripción y precios; folio y RFC quedan en el servidor"


prueba("P1. PDF: nada sensible llega a la IA y el inventario no pierde productos", pdf)
prueba("P2. XML: solo las partidas llegan a la IA (sin proveedor, RFC, domicilio, folio ni sellos)", xml)

for ok, nombre, detalle in resultados:
    print(f"{'✅' if ok else '❌'} {nombre}\n     {detalle}")
fallas = sum(not ok for ok, *_ in resultados)
print(f"\n{len(resultados) - fallas}/{len(resultados)} pruebas de privacidad pasaron")
sys.exit(1 if fallas else 0)
