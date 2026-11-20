"""
Escudo de privacidad para facturas (CFDI).

ANTES de mandar cualquier cosa a la IA (Gemini) se quita todo lo que no sirve para el inventario:
RFC, CURP, nombres y razones sociales, domicilios fiscales y códigos postales, correos, teléfonos, cuentas
bancarias, folio fiscal (UUID), sellos digitales, certificados y cadena original.

Principio de minimización: a la IA solo le llega lo estrictamente necesario para inventariar
(cantidad, unidad, descripción del producto y precios de cada partida). Los datos fiscales que STOCK sí
necesita (folio para no duplicar, total, forma de pago) se leen AQUÍ, en el servidor, y nunca salen.
"""
import re

# (categoría que se le muestra al tendero, patrón, reemplazo). El orden importa: lo más específico primero.
PATRONES = [
    ("cadena original", re.compile(r"\|\|.*?\|\|", re.S), "[cadena original]"),
    ("folio fiscal", re.compile(r"\b[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\b", re.I), "[folio]"),
    ("correos", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[correo]"),
    ("CURP", re.compile(r"\b[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{5}[A-Z\d]\d\b", re.I), "[CURP]"),
    ("RFC", re.compile(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z\d]{3}\b", re.I), "[RFC]"),
    ("sellos y certificados", re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"), "[sello]"),
    ("cuentas y números largos", re.compile(r"(?<![\d.,])\d{11,}(?![\d.,])"), "[número]"),
    ("teléfonos", re.compile(r"(?<![\d.,$])(?:\+?52[\s-]?)?\(?\d{2,3}\)?[\s-]\d{3,4}[\s-]\d{4}(?![\d.,])"), "[teléfono]"),
    ("domicilio fiscal", re.compile(r"\b(?:C\.?\s?P\.?|c[oó]digo postal)\s*:?\s*\d{5}\b", re.I), "[C.P.]"),
    # Nombres de personas que aparecen tras expresiones de entrega o pedido dentro de una descripción
    # (no se usa "para": rompería productos como "BOLSA PARA BASURA")
    ("nombres", re.compile(r"\b(?:entregar\s+a|entrega\s+a|pedido\s+de|de\s+parte\s+de|atenci[oó]n|atn\.?|cliente|"
                          r"recibe)\s*:?\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ.]*(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ.]*){0,3}",
                          re.I), "[nombre]"),
]

# Renglones que por su etiqueta solo traen datos de personas, domicilios o verificación: se quitan completos
ETIQUETAS_SENSIBLES = [
    ("nombres", re.compile(r"raz[oó]n\s+social|\bnombre\b|\breceptor\b|\bemisor\b|\bcliente\b|\batenci[oó]n\b", re.I)),
    ("domicilio fiscal", re.compile(r"domicilio|direcci[oó]n|\bcalle\b|colonia|\bcol\.|municipio|delegaci[oó]n|"
                                    r"alcald[ií]a|localidad|\bestado\s*:|lugar\s+de\s+expedici[oó]n|"
                                    r"\bno\.?\s*(?:ext|int)\b|c[oó]digo\s+postal", re.I)),
    ("correos", re.compile(r"correo|e-?mail", re.I)),
    ("teléfonos", re.compile(r"tel[eé]fono|\btel\b\.?", re.I)),
    ("sellos y certificados", re.compile(r"sello|certificado|no\.?\s*de\s*serie|cadena\s+original|"
                                         r"fecha\s+de\s+timbrado|timbre\s+fiscal", re.I)),
    ("folio fiscal", re.compile(r"folio\s+fiscal|\buuid\b", re.I)),
    ("datos fiscales", re.compile(r"r[eé]gimen\s+fiscal|uso\s+(?:del\s+)?cfdi|\bcurp\b|\brfc\b", re.I)),
    ("cuentas y números largos", re.compile(r"\bclabe\b|cuenta\s+(?:bancaria|ordenante|beneficiaria)|"
                                            r"\bbanco\b|referencia\s+bancaria", re.I)),
]


def limpiar_texto(texto: str, quitado: set) -> str:
    """Reemplaza datos sensibles dentro de un texto (ej. la descripción de una partida)."""
    for categoria, patron, reemplazo in PATRONES:
        texto, n = patron.subn(reemplazo, texto)
        if n:
            quitado.add(categoria)
    return texto


def partidas_minimas(conceptos: list, quitado: set) -> str:
    """CFDI en XML: a la IA SOLO le llegan las partidas (sin proveedor, RFC, domicilios, folio ni sellos)."""
    lineas = ["Partidas de la factura del proveedor:"]
    for c in conceptos:
        descripcion = limpiar_texto(c["descripcion"], quitado)
        lineas.append(
            f"Partida {c['partida']}: {c['cantidad']:g} {c['unidad']} de \"{descripcion}\" "
            f"(precio por {c['unidad'] or 'unidad'}: ${c['valor_unitario']:,.2f}, importe ${c['importe']:,.2f}"
            + (f", ya con descuento de ${c['descuento']:,.2f}" if c.get("descuento") else "") + ")"
        )
    return "\n".join(lineas)


def _parece_partida(linea: str) -> bool:
    """Un renglón útil para inventariar trae al menos un número (cantidad o precio) y alguna palabra."""
    return bool(re.search(r"\d", linea)) and bool(re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{2,}", linea))


def _quitar_notas_sensibles(linea: str, quitado: set) -> str:
    """En un renglón de producto, borra notas entre paréntesis o tras etiquetas que traen datos de personas
    ("(pedido de Juan Pérez, tel …)"), sin tocar la descripción, la cantidad ni los precios."""
    def nota(m):
        contenido = m.group(0)
        cat = next((c for c, patron in ETIQUETAS_SENSIBLES if patron.search(contenido)), None)
        if cat or re.search(r"pedido\s+de|para\s+[A-ZÁÉÍÓÚ]|de\s+parte", contenido, re.I):
            quitado.add(cat or "nombres")
            return ""
        return contenido
    return re.sub(r"\([^)]*\)|\[[^\]]*\]", nota, linea)


def texto_minimo_pdf(texto: str, quitado: set) -> str:
    """CFDI en PDF: se queda solo con los renglones de productos y totales, ya limpios.
    Quita renglones de nombres, domicilios, sellos, folio, etc. y luego borra lo sensible que quede suelto."""
    utiles = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        if re.search(r"\d+\.\d{2}\b", linea):  # renglón de producto (trae precio): se conserva y solo se limpia
            linea = _quitar_notas_sensibles(linea, quitado)
        else:
            sensible = next((cat for cat, patron in ETIQUETAS_SENSIBLES if patron.search(linea)), None)
            if sensible:  # renglón de nombres, domicilios, sellos, folio…: fuera completo
                quitado.add(sensible)
                continue
        linea = limpiar_texto(linea, quitado)
        if re.fullmatch(r"(?:\[[^\]]+\][\s,.;:|-]*)+", linea):  # el renglón solo traía datos sensibles
            continue
        if _parece_partida(linea) or re.search(r"cant|descrip|unidad|precio|importe|total", linea, re.I):
            utiles.append(linea)
    return "\n".join(utiles)


def datos_locales_pdf(texto: str) -> dict:
    """Lo que STOCK necesita de un PDF y se lee AQUÍ (nunca se manda a la IA): folio, total y forma de pago."""
    folio = re.search(r"\b[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\b", texto, re.I)
    total = None
    for m in re.finditer(r"\btotal\b[^\d\n]{0,25}\$?\s*([\d,]+\.\d{2})", texto, re.I):
        total = m.group(1)  # el último "Total" suele ser el de la factura (no el subtotal)
    forma = re.search(r"forma\s+de\s+pago\D{0,15}(\d{2})", texto, re.I)
    emisor = re.search(r"^\s*([A-ZÁÉÍÓÚÑ0-9&.,\- ]{6,90}?(?:S\.?A\.?|S\. ?DE R\.?L\.?|SA DE CV|S DE RL)[A-Z .]*)$",
                       texto, re.M)
    return {
        "uuid": folio.group(0).upper() if folio else None,
        "total": float(total.replace(",", "")) if total else 0.0,
        "forma_pago": forma.group(1) if forma else None,
        "proveedor": emisor.group(1).strip()[:120] if emisor else "Proveedor",
    }


ETIQUETA_CATEGORIA = {
    "RFC": "RFC", "CURP": "CURP", "nombres": "nombres y razón social", "domicilio fiscal": "domicilio fiscal",
    "correos": "correos", "teléfonos": "teléfonos", "folio fiscal": "folio fiscal",
    "sellos y certificados": "sellos y certificados digitales", "cadena original": "cadena original",
    "datos fiscales": "régimen y uso del CFDI", "cuentas y números largos": "cuentas bancarias",
}


def resumen(quitado: set, partidas: int) -> dict:
    orden = list(ETIQUETA_CATEGORIA)
    lista = [ETIQUETA_CATEGORIA[c] for c in sorted(quitado, key=lambda c: orden.index(c) if c in orden else 99)]
    return {"protegido": lista,
            "enviado_a_ia": f"solo cantidad, unidad, descripción y precio de {partidas} "
                            f"{'partida' if partidas == 1 else 'partidas'}"}
