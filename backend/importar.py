# =====================================================================================================
# 📥 importar.py — leer el Excel o CSV del tendero aunque venga como venga (títulos, filas de TOTAL, columnas raras)
# =====================================================================================================
"""
Importar el inventario que la tienda ya tiene en Excel (.xlsx) o CSV.

Cada tienda nombra sus columnas distinto ("Producto", "Artículo", "Existencia", "Cant.", "P. Venta"...).
Flujo:
  1. leer_tabla(): lee el archivo y encuentra la fila de encabezados.
  2. Mapeo de columnas: Gemini decide qué columna es nombre/cantidad/precio/... (en main.py);
     si falla, mapear_heuristico() usa palabras clave.
  3. extraer_productos(): convierte las filas en productos limpios.
"""
import csv
import io
import re
import unicodedata

# 👉 Los campos que buscamos en el Excel
CAMPOS = ["nombre", "cantidad", "unidad", "precio", "costo", "minimo", "categoria"]

# 👉 Palabras que delatan cada columna ('existencia', 'cuántos me quedan' → cantidad, etc.)
PALABRAS = {
    "nombre": ["producto", "articulo", "descripcion", "nombre", "item", "concepto", "mercancia"],
    "cantidad": ["existencia", "cantidad", "cant", "stock", "inventario", "piezas", "disponible", "hay"],
    "unidad": ["unidad", "u.m", "um", "medida", "presentacion"],
    "precio": ["precio venta", "p. venta", "pventa", "precio publico", "precio", "venta", "pvp"],
    "costo": ["costo", "precio compra", "p. compra", "compra"],
    "minimo": ["minimo", "min", "stock minimo", "reorden", "punto de reorden"],
    "categoria": ["categoria", "departamento", "depto", "familia", "linea", "tipo", "seccion"],
}


# 👉 Minúsculas y sin acentos para comparar encabezados
def _norm(texto) -> str:
    texto = unicodedata.normalize("NFD", str(texto or "").lower().strip())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


# 👉 Abre el Excel/CSV, encuentra dónde empiezan los encabezados y regresa encabezados + filas
def leer_tabla(contenido: bytes, nombre_archivo: str) -> tuple[list, list]:
    """Devuelve (encabezados, filas) del primer hoja/archivo."""
    nombre = nombre_archivo.lower()
    if nombre.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        hoja = libro.worksheets[0]
        crudas = [list(f) for f in hoja.iter_rows(values_only=True)]
    elif nombre.endswith((".csv", ".txt")):
        texto = None
        for codificacion in ("utf-8-sig", "latin-1"):
            try:
                texto = contenido.decode(codificacion)
                break
            except UnicodeDecodeError:
                continue
        dialecto = csv.Sniffer().sniff(texto[:2000], delimiters=",;\t") if texto else csv.excel
        crudas = list(csv.reader(io.StringIO(texto), dialecto))
    elif nombre.endswith(".xls"):
        raise ValueError("Archivo .xls antiguo: ábrelo en Excel y guárdalo como .xlsx")
    else:
        raise ValueError("Formato no soportado: sube un .xlsx o .csv")

    crudas = [f for f in crudas if any(c not in (None, "") for c in f)]
    if not crudas:
        raise ValueError("El archivo está vacío")

    # Encabezado = primera fila con al menos 2 celdas de texto (a veces hay un título arriba)
    idx = 0
    for i, fila in enumerate(crudas[:10]):
        textos = [c for c in fila if isinstance(c, str) and c.strip() and not _es_numero(c)]
        if len(textos) >= 2:
            idx = i
            break
    encabezados = [str(c).strip() if c is not None else "" for c in crudas[idx]]
    filas = crudas[idx + 1:]
    return encabezados, filas


# 👉 ¿Esta celda es un número? (acepta $ y comas)
def _es_numero(valor) -> bool:
    """True solo si TODO el valor es un número ("12", "$1,250.50"). "Coca-Cola 600 ml" NO es número."""
    if isinstance(valor, (int, float)):
        return True
    return bool(re.fullmatch(r"\s*\$?\s*-?[\d.,]+\s*", str(valor or ""))) and _a_numero(valor) is not None


# 👉 Convierte '$1,234.50' a 1234.5
def _a_numero(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    limpio = re.sub(r"[^\d.,\-]", "", str(valor))
    if not limpio:
        return None
    if "," in limpio and "." in limpio:
        limpio = limpio.replace(",", "")
    elif "," in limpio:
        limpio = limpio.replace(",", ".")
    try:
        return float(limpio)
    except ValueError:
        return None


# 👉 Adivina qué columna es cuál con las PALABRAS (si no alcanza, main.py le pregunta a la IA)
def mapear_heuristico(encabezados: list) -> dict:
    """Plan B sin IA: busca palabras clave en los encabezados."""
    mapa = {}
    usados = set()
    for campo in ["costo", "precio", "minimo", "cantidad", "nombre", "unidad", "categoria"]:
        for i, h in enumerate(encabezados):
            if i in usados:
                continue
            hn = _norm(h)
            if any(p in hn for p in PALABRAS[campo]):
                mapa[campo] = i
                usados.add(i)
                break
    return mapa


# 👉 ¿Se vende por pieza o por kilo? (por la columna o por el nombre del producto)
def _unidad(valor, nombre: str) -> str:
    u = _norm(valor)
    if u in ("kg", "kilo", "kilos", "kilogramo", "kilogramos", "kgs") or "kg" in u:
        return "kg"
    if u in ("l", "lt", "lts", "litro", "litros"):
        return "litro"
    if not u and re.search(r"\b(granel|kilo|kilos|kg)\b|\(kg\)|\(kilo\)", _norm(nombre)):
        return "kg"
    return "pieza"


# 👉 Convierte las filas en productos y separa las que no sirven (vacías, TOTAL, etc.)
def extraer_productos(filas: list, mapa: dict) -> tuple[list, list]:
    """Convierte filas en productos. Devuelve (productos, filas_ignoradas)."""
    def celda(fila, campo):
        i = mapa.get(campo)
        return fila[i] if i is not None and i < len(fila) else None

    productos, ignoradas = [], []
    vistos = {}
    for n, fila in enumerate(filas, start=1):
        nombre = celda(fila, "nombre")
        nombre = str(nombre).strip() if nombre is not None else ""
        cantidad = _a_numero(celda(fila, "cantidad"))
        if not nombre or _es_numero(nombre) or _norm(nombre) in ("total", "totales", "suma"):
            if nombre or cantidad is not None:
                ignoradas.append({"fila": n, "motivo": "sin nombre de producto o fila de total"})
            continue
        if cantidad is None:
            cantidad = 0
        precio = _a_numero(celda(fila, "precio"))
        minimo = _a_numero(celda(fila, "minimo"))
        if minimo is None:  # si no lo traen, sugerimos 20 % de lo que hay (mínimo 1)
            minimo = max(1.0, round(cantidad * 0.2))
        producto = {
            "nombre": nombre[:80],
            "cantidad": round(max(0.0, cantidad), 3),
            "unidad": _unidad(celda(fila, "unidad"), nombre),
            "precio": precio,
            "costo": _a_numero(celda(fila, "costo")),
            "minimo": minimo,
            "categoria": (str(celda(fila, "categoria")).strip() or None) if celda(fila, "categoria") else None,
        }
        clave = _norm(nombre)
        if clave in vistos:  # el mismo producto en dos filas: sumamos existencias
            vistos[clave]["cantidad"] += producto["cantidad"]
            continue
        vistos[clave] = producto
        productos.append(producto)
    return productos, ignoradas
