# =====================================================================================================
# 🧾 cfdi.py — lee facturas electrónicas del SAT (CFDI 3.3 y 4.0) en XML, de forma segura
# Solo sacamos lo que sirve para el inventario y anotamos qué datos sensibles traía (para no mandarlos a la IA).
# =====================================================================================================
"""
Lectura de facturas electrónicas (CFDI 3.3 y 4.0) en XML.

Seguridad (XXE / XML bombs / "billion laughs"):
  1. Antes de parsear se rechaza cualquier <!DOCTYPE o <!ENTITY (un CFDI legítimo nunca los trae).
  2. El parseo se hace con defusedxml, que bloquea entidades externas y expansiones maliciosas.

Solo se extrae lo que sirve para el inventario: quién vende, cuánto se pagó, cómo se pagó,
el folio único de la factura y las partidas (cantidad, unidad, descripción, precio).
"""
import hashlib
import re

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

# 👉 Si el XML trae DOCTYPE o ENTITY lo rechazamos de volada: así se hacen los ataques XXE
_PELIGROSO = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
# Claves de unidad del SAT que indican servicio, no mercancía (E48 = unidad de servicio, ACT = actividad,
# E51 = trabajo, A9 = tarifa)
# 👉 Claves de unidad del SAT que son servicios (flete, trabajo…), no mercancía
CLAVES_SERVICIO = {"E48", "ACT", "E51", "A9"}
# En el catálogo c_ClaveProdServ del SAT, los segmentos 70 a 95 son servicios (fletes 78, rentas 80, etc.)
# 👉 En el catálogo del SAT, las claves de producto 70-95 son servicios
SEGMENTO_SERVICIOS = range(70, 96)
# Solo la factura de INGRESO (I) es una compra de mercancía. E = nota de crédito, P = pago, T = traslado, N = nómina
# 👉 Solo la factura de Ingreso (I) es compra. Nota de crédito, pago, traslado y nómina se rechazan
TIPOS_NO_COMPRA = {
    "E": "Este XML es una nota de crédito (descuento o devolución), no una compra. No cambié tu inventario.",
    "P": "Este XML es un comprobante de pago, no trae mercancía. No cambié tu inventario.",
    "T": "Este XML es un traslado de mercancía, no una compra. No cambié tu inventario.",
    "N": "Este XML es un recibo de nómina, no una factura de proveedor.",
}


# 👉 Quita el namespace de la etiqueta: '{http://sat...}Concepto' → 'Concepto'
def _local(tag: str) -> str:
    """'{http://www.sat.gob.mx/cfd/4}Concepto' -> 'Concepto' (ignora el prefijo del namespace)."""
    return tag.rsplit("}", 1)[-1]


# 👉 Lee un atributo sin importar mayúsculas (3.3 y 4.0 se escriben distinto a veces)
def _attr(elemento, *nombres, default=None):
    """Lee un atributo sin importar mayúsculas/minúsculas (CFDI 3.3 y 4.0 usan los mismos nombres)."""
    mapa = {k.lower(): v for k, v in elemento.attrib.items()}
    for n in nombres:
        if n.lower() in mapa:
            return mapa[n.lower()]
    return default


# 👉 Texto a número sin tronar (si viene raro, regresa el default)
def _num(valor, default=0.0) -> float:
    try:
        return float(str(valor).replace(",", ""))
    except (TypeError, ValueError):
        return default


# 👉 📄 Lee el CFDI: proveedor, total, folio, partidas (con descuentos y moneda) y qué datos sensibles traía
def leer_cfdi(contenido: bytes) -> dict:
    """Devuelve {uuid, proveedor, rfc, total, forma_pago, fecha, conceptos[]}. Lanza ValueError si no es un CFDI."""
    if _PELIGROSO.search(contenido):
        raise ValueError("Por seguridad no aceptamos XML con DOCTYPE o ENTITY (una factura real no los trae)")
    try:
        raiz = fromstring(contenido, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as e:
        raise ValueError("Por seguridad rechazamos este XML (trae construcciones peligrosas)") from e
    except ParseError as e:
        raise ValueError("El archivo no es un XML válido") from e
    if _local(raiz.tag) != "Comprobante":
        raise ValueError("Este XML no parece una factura (no encontré el Comprobante)")
    tipo = (_attr(raiz, "TipoDeComprobante") or "I").strip().upper()[:1]
    if tipo in TIPOS_NO_COMPRA:
        raise ValueError(TIPOS_NO_COMPRA[tipo])
    # Facturas en otra moneda: se convierten a pesos con el tipo de cambio de la propia factura
    moneda = (_attr(raiz, "Moneda") or "MXN").strip().upper()
    cambio = _num(_attr(raiz, "TipoCambio"), 1.0) if moneda not in ("MXN", "XXX") else 1.0
    cambio = cambio if 0 < cambio < 1000 else 1.0

    emisor = timbre = None
    conceptos = []
    sensibles = set()  # qué datos personales o de verificación traía (nunca se mandan a la IA)
    if _attr(raiz, "Sello") or _attr(raiz, "Certificado") or _attr(raiz, "NoCertificado"):
        sensibles.add("sellos y certificados")
    if _attr(raiz, "LugarExpedicion"):
        sensibles.add("domicilio fiscal")
    for el in raiz.iter():
        nombre = _local(el.tag)
        if nombre in ("Emisor", "Receptor"):
            if _attr(el, "Rfc"):
                sensibles.add("RFC")
            if _attr(el, "Nombre"):
                sensibles.add("nombres")
            if _attr(el, "DomicilioFiscalReceptor"):
                sensibles.add("domicilio fiscal")
            if _attr(el, "RegimenFiscal", "RegimenFiscalReceptor", "UsoCFDI"):
                sensibles.add("datos fiscales")
        if nombre == "Emisor" and emisor is None:
            emisor = el
        elif nombre == "TimbreFiscalDigital":
            timbre = el
            sensibles.update({"folio fiscal", "sellos y certificados"})
        elif nombre == "Concepto":
            clave_unidad = (_attr(el, "ClaveUnidad") or "").strip().upper()
            unidad = (_attr(el, "Unidad") or clave_unidad or "")[:20]
            clave_prod = re.sub(r"\D", "", _attr(el, "ClaveProdServ") or "")
            es_servicio = (clave_unidad in CLAVES_SERVICIO or "servicio" in unidad.lower()
                           or (len(clave_prod) == 8 and int(clave_prod[:2]) in SEGMENTO_SERVICIOS))
            importe = _num(_attr(el, "Importe"))
            descuento = max(0.0, _num(_attr(el, "Descuento"), 0.0))
            conceptos.append({
                "partida": len(conceptos) + 1,
                "cantidad": _num(_attr(el, "Cantidad"), 1),
                "unidad": unidad,
                "clave_unidad": clave_unidad,
                # Servicios (fletes, estadías, rentas, comisiones…) no son mercancía para el inventario
                "es_servicio": es_servicio,
                "descripcion": (_attr(el, "Descripcion") or "").strip()[:150],
                "valor_unitario": round(_num(_attr(el, "ValorUnitario")) * cambio, 4),
                # Lo que de verdad se pagó por la partida: importe menos descuento, en pesos
                "importe": round(max(0.0, importe - descuento) * cambio, 2),
                "descuento": round(descuento * cambio, 2),
            })
    if not conceptos:
        raise ValueError("La factura no trae productos (conceptos)")
    if len(conceptos) > 300:
        raise ValueError("La factura trae demasiadas partidas para procesarla de una vez")

    uuid = _attr(timbre, "UUID") if timbre is not None else None
    if not uuid:  # factura sin timbrar: usamos una huella del archivo para no duplicar
        uuid = "SIN-TIMBRE-" + hashlib.sha256(contenido).hexdigest()[:16]

    return {
        "uuid": re.sub(r"[^A-Za-z0-9\-]", "", uuid).upper()[:64],
        "proveedor": ((_attr(emisor, "Nombre") or _attr(emisor, "Rfc") or "Proveedor") if emisor is not None
                      else "Proveedor")[:120],
        "rfc": _attr(emisor, "Rfc") if emisor is not None else None,
        "total": round(_num(_attr(raiz, "Total")) * cambio, 2),
        "moneda": moneda,
        "forma_pago": _attr(raiz, "FormaPago"),
        "fecha": _attr(raiz, "Fecha"),
        "conceptos": conceptos,
        "sensibles": sensibles,
    }
