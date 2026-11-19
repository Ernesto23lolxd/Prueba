"""
Backend del asistente de inventario por voz.

Ejecutar (desde la carpeta backend):
    pip install -r requirements.txt
    set GEMINI_API_KEY=tu_clave        (PowerShell: $env:GEMINI_API_KEY="tu_clave")
    python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Abrir: http://localhost:8000
"""
import difflib
import json
import math
import os
import random
import sqlite3
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import quote
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import importar

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR.parent / "app"

# Cargar variables desde backend/.env (ej. GEMINI_API_KEY=...) sin librerías extra
_env = BASE_DIR / ".env"
if _env.exists():
    for _linea in _env.read_text(encoding="utf-8-sig").splitlines():
        if "=" in _linea and not _linea.strip().startswith("#"):
            _k, _v = _linea.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

DB_PATH = BASE_DIR / "inventario.db"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

app = FastAPI(title="Inventario por voz")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- Base de datos
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


PRODUCTOS_DEMO = [
    # nombre, unidad, cantidad actual, minimo, precio, categoria, venta diaria promedio (para el historial)
    ("Coca-Cola 600 ml", "pieza", 30, 12, 22, "Bebidas", 14),
    ("Coca-Cola 2.5 L", "pieza", 10, 4, 48, "Bebidas", 3),
    ("Agua Ciel 1 L", "pieza", 20, 8, 15, "Bebidas", 5),
    ("Sabritas sal 45 g", "pieza", 18, 10, 20, "Botanas", 6),
    ("Galletas Marías", "pieza", 12, 6, 18, "Botanas", 1.5),
    ("Huevo", "kg", 6, 3, 48, "Básicos", 2.5),
    ("Tortillas", "kg", 10, 4, 24, "Tortillería", 6),
    ("Leche Lala 1 L", "pieza", 8, 8, 29, "Lácteos", 5),
    ("Pan Bimbo grande", "pieza", 4, 4, 52, "Panadería", 2),
    ("Jamón de pavo", "kg", 1.5, 0.5, 160, "Salchichonería", 0.4),
    ("Frijol pinto", "kg", 15, 5, 32, "Granel", 1.5),
    ("Arroz", "kg", 9, 4, 28, "Granel", 1),
    ("Azúcar", "kg", 7, 3, 30, "Granel", 0.8),
    ("Aceite 1-2-3 1 L", "pieza", 6, 3, 45, "Abarrotes", 0.7),
    ("Maruchan", "pieza", 24, 10, 15, "Abarrotes", 4),
    ("Atún Dolores", "pieza", 9, 5, 26, "Abarrotes", 1),
    ("Café Nescafé 42 g", "pieza", 5, 2, 42, "Abarrotes", 0.3),
    ("Ate de membrillo", "pieza", 5, 2, 35, "Dulces", 0.3),
    ("Papel higiénico 4 rollos", "pieza", 8, 4, 38, "Limpieza", 0.6),
    ("Jabón Zote", "pieza", 10, 4, 22, "Limpieza", 0.5),
]

# Las tienditas venden más en fin de semana (lunes=0 ... domingo=6)
FACTOR_DIA = {0: 0.9, 1: 0.85, 2: 0.9, 3: 0.95, 4: 1.15, 5: 1.4, 6: 1.3}
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_HISTORIAL = 14
# Para cuántos días conviene comprar: lo perecedero se surte seguido, lo demás para 1 semana
COBERTURA_DIAS = {"Tortillería": 1, "Panadería": 2, "Lácteos": 3, "Salchichonería": 4}
COBERTURA_DEFAULT = 7


def init_db(reset: bool = False):
    con = db()
    if reset:
        con.executescript("DROP TABLE IF EXISTS movimientos; DROP TABLE IF EXISTS productos;")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            unidad TEXT NOT NULL DEFAULT 'pieza',
            cantidad REAL NOT NULL DEFAULT 0,
            minimo REAL NOT NULL DEFAULT 0,
            precio REAL,
            categoria TEXT,
            costo REAL
        );
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER REFERENCES productos(id),
            tipo TEXT NOT NULL,            -- entrada | venta | ajuste | alta
            cantidad REAL NOT NULL,
            fecha TEXT NOT NULL,
            texto_original TEXT
        );
        """
    )
    columnas = [c["name"] for c in con.execute("PRAGMA table_info(productos)").fetchall()]
    if "costo" not in columnas:  # bases creadas antes de esta versión
        con.execute("ALTER TABLE productos ADD COLUMN costo REAL")
    if con.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
        cargar_demo(con)
    con.commit()
    con.close()


def cargar_demo(con):
    """Productos de una tiendita de Durango + 2 semanas de ventas simuladas (siempre las mismas)."""
    rnd = random.Random(2026)
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for nombre, unidad, cantidad, minimo, precio, categoria, diaria in PRODUCTOS_DEMO:
        con.execute(
            "INSERT INTO productos (nombre, unidad, cantidad, minimo, precio, categoria) VALUES (?,?,?,?,?,?)",
            (nombre, unidad, cantidad, minimo, precio, categoria),
        )
        pid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        for atras in range(DIAS_HISTORIAL, 0, -1):
            dia = hoy - timedelta(days=atras)
            total = diaria * FACTOR_DIA[dia.weekday()] * rnd.uniform(0.75, 1.25)
            # Se vende en "pasos": piezas enteras o cuartos de kilo. Redondeo aleatorio para respetar el promedio.
            paso = 0.25 if unidad == "kg" else 1
            pasos = total / paso
            pasos = int(pasos) + (1 if rnd.random() < pasos - int(pasos) else 0)
            while pasos > 0:
                bloque = min(pasos, rnd.randint(1, 4 if unidad == "kg" else 3))
                pasos -= bloque
                cant = bloque * paso
                momento = dia + timedelta(hours=rnd.randint(8, 21), minutes=rnd.randint(0, 59))
                con.execute(
                    "INSERT INTO movimientos (producto_id, tipo, cantidad, fecha, texto_original) VALUES (?,?,?,?,?)",
                    (pid, "venta", cant, momento.isoformat(timespec="seconds"), "(historial de demo)"),
                )


init_db()


def estado(p) -> str:
    if p["cantidad"] <= 0:
        return "agotado"
    if p["cantidad"] <= p["minimo"]:
        return "bajo"
    if p["cantidad"] <= p["minimo"] * 1.5:
        return "atencion"
    return "ok"


def listar_productos():
    con = db()
    filas = con.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    con.close()
    return [{**dict(f), "estado": estado(f)} for f in filas]


def _redondear_compra(cant: float, unidad: str) -> float:
    if cant <= 0:
        return 0
    return math.ceil(cant * 2) / 2 if unidad == "kg" else math.ceil(cant)


def _cuando(dias: int, fecha: datetime) -> str:
    if dias == 0:
        return "hoy"
    if dias == 1:
        return "mañana"
    if dias < 7:
        return f"el {DIAS_SEMANA[fecha.weekday()]}"
    return f"en {dias} días"


def calcular_prediccion() -> list:
    """Para cada producto: cuánto se vende al día, cuándo se acaba y cuánto conviene comprar.

    Método (explicable a los jueces): promedio de ventas de los últimos 14 días, ajustado
    porque en fin de semana se vende más. Se simula día por día hasta que se acaba.
    """
    ahora = datetime.now()
    desde = (ahora - timedelta(days=DIAS_HISTORIAL)).isoformat(timespec="seconds")
    con = db()
    ventas = con.execute(
        "SELECT producto_id, SUM(cantidad) AS total, MIN(fecha) AS primera FROM movimientos "
        "WHERE tipo='venta' AND fecha >= ? GROUP BY producto_id",
        (desde,),
    ).fetchall()
    con.close()
    por_producto = {v["producto_id"]: v for v in ventas}

    # Qué parte del día de hoy queda (la tienda abre de 8:00 a 22:00)
    resto_hoy = min(1.0, max(0.0, (22 - (ahora.hour + ahora.minute / 60)) / 14))

    resultado = []
    for p in listar_productos():
        v = por_producto.get(p["id"])
        if not v or not v["total"]:
            resultado.append({**p, "venta_diaria": 0, "dias_restantes": None, "se_acaba": None,
                              "se_acaba_texto": "sin ventas recientes", "comprar": 0, "urgencia": "baja"})
            continue
        dias_obs = (ahora - datetime.fromisoformat(v["primera"])).total_seconds() / 86400
        promedio = v["total"] / min(DIAS_HISTORIAL, max(1.0, dias_obs))

        restante = p["cantidad"]
        dias = None
        consumo_hoy = promedio * FACTOR_DIA[ahora.weekday()] * resto_hoy
        if restante <= consumo_hoy:
            dias = 0
        else:
            restante -= consumo_hoy
            for d in range(1, 61):
                consumo = promedio * FACTOR_DIA[(ahora + timedelta(days=d)).weekday()]
                if restante <= consumo:
                    dias = d
                    break
                restante -= consumo

        cobertura = COBERTURA_DIAS.get(p["categoria"], COBERTURA_DEFAULT)
        necesidad = sum(promedio * FACTOR_DIA[(ahora + timedelta(days=d)).weekday()] for d in range(1, cobertura + 1))
        comprar = _redondear_compra(necesidad + p["minimo"] - p["cantidad"], p["unidad"])
        fecha_fin = ahora + timedelta(days=dias) if dias is not None else None
        if p["estado"] in ("bajo", "agotado") or (dias is not None and dias <= 1):
            urgencia = "alta"
        elif dias is not None and dias <= 3:
            urgencia = "media"
        else:
            urgencia = "baja"

        resultado.append({
            **p,
            "venta_diaria": round(promedio, 2),
            "dias_restantes": dias,
            "se_acaba": fecha_fin.date().isoformat() if fecha_fin else None,
            "se_acaba_texto": _cuando(dias, fecha_fin) if dias is not None else "en más de 2 meses",
            "comprar": comprar,
            "urgencia": urgencia,
        })

    orden = {"alta": 0, "media": 1, "baja": 2}
    resultado.sort(key=lambda r: (orden[r["urgencia"]], r["dias_restantes"] if r["dias_restantes"] is not None else 999))
    return resultado


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower().strip())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def buscar_producto(con, nombre: str):
    """Busca el producto por nombre exacto o parecido (tolera errores del dictado)."""
    filas = con.execute("SELECT * FROM productos").fetchall()
    mapa = {normalizar(f["nombre"]): f for f in filas}
    clave = normalizar(nombre)
    if clave in mapa:
        return mapa[clave]
    for k, f in mapa.items():  # "coca" -> "coca-cola 600 ml"
        if clave and (clave in k or k in clave):
            return f
    parecidos = difflib.get_close_matches(clave, list(mapa), n=1, cutoff=0.6)
    return mapa[parecidos[0]] if parecidos else None


# ---------------------------------------------------------------- Lógica de acciones
def aplicar_acciones(acciones: list, texto_original: str) -> list:
    """Aplica las acciones que interpretó la IA. Devuelve lo que realmente pasó."""
    resultados = []
    con = db()
    ahora = datetime.now().isoformat(timespec="seconds")
    for a in acciones:
        tipo = (a.get("tipo") or "").lower()
        nombre = a.get("producto") or ""
        cantidad = float(a.get("cantidad") or 0)
        if tipo == "consultar" or not nombre:
            continue
        p = buscar_producto(con, nombre)

        if p is None:
            if tipo in ("entrada", "ajuste", "alta"):
                con.execute(
                    "INSERT INTO productos (nombre, unidad, cantidad, minimo, precio, categoria) VALUES (?,?,?,?,?,?)",
                    (nombre.strip().capitalize(), a.get("unidad") or "pieza", cantidad,
                     float(a.get("minimo") or 0), a.get("precio"), a.get("categoria")),
                )
                pid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
                con.execute(
                    "INSERT INTO movimientos (producto_id, tipo, cantidad, fecha, texto_original) VALUES (?,?,?,?,?)",
                    (pid, "alta", cantidad, ahora, texto_original),
                )
                resultados.append({"producto": nombre, "tipo": "alta", "cantidad": cantidad, "ok": True})
            else:
                resultados.append({"producto": nombre, "tipo": tipo, "ok": False,
                                   "error": "No encontré ese producto en el inventario"})
            continue

        if tipo == "entrada":
            nueva = p["cantidad"] + cantidad
        elif tipo == "venta":
            if cantidad > p["cantidad"]:
                # Protección: no vender más de lo que hay (suele ser un error de unidades)
                resultados.append({"producto": p["nombre"], "tipo": "venta", "ok": False,
                                   "error": f"Solo hay {p['cantidad']:g} {p['unidad']}, no {cantidad:g}"})
                continue
            nueva = p["cantidad"] - cantidad
        elif tipo == "ajuste":
            nueva = cantidad
        elif tipo == "minimo":
            con.execute("UPDATE productos SET minimo=? WHERE id=?", (cantidad, p["id"]))
            resultados.append({"producto": p["nombre"], "tipo": "minimo", "cantidad": cantidad, "ok": True})
            continue
        elif tipo == "precio":
            # La IA puede mandar el precio en "precio" o en "cantidad"
            valor = a.get("precio") if a.get("precio") not in (None, 0, "") else cantidad
            if not valor:
                resultados.append({"producto": p["nombre"], "tipo": "precio", "ok": False,
                                   "error": "No entendí el precio nuevo"})
                continue
            con.execute("UPDATE productos SET precio=? WHERE id=?", (float(valor), p["id"]))
            resultados.append({"producto": p["nombre"], "tipo": "precio", "cantidad": float(valor), "ok": True})
            continue
        else:
            continue

        nueva = round(nueva, 3)
        con.execute("UPDATE productos SET cantidad=? WHERE id=?", (nueva, p["id"]))
        con.execute(
            "INSERT INTO movimientos (producto_id, tipo, cantidad, fecha, texto_original) VALUES (?,?,?,?,?)",
            (p["id"], tipo, cantidad, ahora, texto_original),
        )
        resultados.append({"producto": p["nombre"], "tipo": tipo, "cantidad": cantidad,
                           "antes": p["cantidad"], "ahora": nueva, "unidad": p["unidad"], "ok": True})
    con.commit()
    con.close()
    return resultados


# ---------------------------------------------------------------- Gemini
PROMPT = """Eres "Surtí", el asistente de inventario por voz de una tiendita en Durango, México.
El dueño te habla de forma natural (puede usar modismos, diminutivos o errores).
Tu trabajo: entender qué quiere hacer con su inventario y devolver SOLO un JSON.

INVENTARIO ACTUAL (nombre | unidad | cantidad | mínimo | precio):
{inventario}

Tipos de acción posibles:
- "entrada": llegó mercancía / surtió / compró al proveedor (suma).
- "venta": vendió / se llevaron / salió (resta).
- "ajuste": dice cuánto hay en total ("me quedan 5", "hay 10 kilos") (reemplaza).
- "alta": producto nuevo que no existe en el inventario.
- "minimo": define la cantidad mínima antes de avisar.
- "precio": cambia el precio.
- "consultar": solo pregunta (cuánto queda, qué se acaba, qué debo comprar, cuánto vale el inventario).
- "enviar_lista": pide mandar/compartir la lista de compras o el pedido por WhatsApp o al proveedor
  (ej. "mándale la lista al proveedor", "pásame el pedido por WhatsApp"). No lleva producto.
  TÚ NO PUEDES ENVIAR MENSAJES: di que dejaste el pedido listo y que toque el botón verde para mandarlo
  por WhatsApp (ej. "Te dejé listo el pedido con 9 productos, toca el botón verde para mandarlo").

Reglas:
- Usa EXACTAMENTE el nombre del inventario si el producto ya existe ("coca" -> "Coca-Cola 600 ml").
- Convierte cantidades: "una docena" = 12, "medio kilo" = 0.5, "un cartón de huevo" = 30 piezas o ~1.8 kg según la unidad del producto.
- IMPORTANTE: "cantidad" SIEMPRE va en la unidad del producto en el inventario. Si el producto está en kg y te dicen
  piezas o docenas, convierte a kg (1 huevo ≈ 0.06 kg, 1 docena de huevo ≈ 0.72 kg).
- Si dice cajas/paquetes y no sabes cuántas piezas trae, pregunta en "respuesta" y no inventes la acción.
- Para cambiar precio usa tipo "precio" y pon el precio nuevo en "precio".
- NO hagas sumas ni multiplicaciones tú: usa el VALOR TOTAL y los valores ya calculados del inventario.
- "¿Cuándo se me acaba X?" -> usa la columna "se acaba" y "vende ~/día" (ej. "se te acaba el sábado, vendes como 2.5 kilos al día").
- "¿Qué tengo que comprar?" / "¿qué surto?" -> usa la LISTA DE COMPRAS SUGERIDA y SIEMPRE di la cantidad de cada uno
  (ej. "compra 40 leches, 39 kilos de tortilla y 17 panes"). Menciona máximo 5 productos.
- La respuesta se va a escuchar: redondea los números como habla la gente ("como 15 al día", "casi 3 kilos"),
  nunca digas decimales como 2.68 o 15.09.
- Al confirmar una venta, si ese producto se acaba hoy o mañana según la predicción, avísale.
- "respuesta": frase corta, amable y hablada (se leerá en voz alta), en español de México. Confirma lo que hiciste
  y, si algún producto queda en o bajo su mínimo, avísale. Para consultas, responde con los datos del inventario.
- "transcripcion": lo que entendiste que dijo el usuario.

Formato EXACTO:
{{"transcripcion": "...", "acciones": [{{"tipo": "...", "producto": "...", "cantidad": 0, "unidad": "...", "precio": null}}], "respuesta": "..."}}
"""


def texto_inventario() -> str:
    """Inventario para la IA, con los cálculos ya hechos (la IA no debe sumar)."""
    prods = calcular_prediccion()
    lineas = [
        f"- {p['nombre']} | {p['unidad']} | {p['cantidad']:g} | {p['minimo']:g} | {p['precio']} "
        f"| valor ${(p['cantidad'] * (p['precio'] or 0)):,.2f} | estado: {p['estado']} "
        f"| vende ~{p['venta_diaria']:g}/día | se acaba: {p['se_acaba_texto']} | sugerido comprar: {p['comprar']:g}"
        for p in prods
    ]
    total = sum(p["cantidad"] * (p["precio"] or 0) for p in prods)
    bajos = [p["nombre"] for p in prods if p["estado"] in ("bajo", "agotado")]
    compras = [f"{p['comprar']:g} {p['unidad']} de {p['nombre']}" for p in prods
               if p["urgencia"] in ("alta", "media") and p["comprar"] > 0]
    ahora = datetime.now()
    lineas.append(f"\nHOY ES {DIAS_SEMANA[ahora.weekday()].upper()} {ahora:%d/%m/%Y} {ahora:%H:%M}")
    lineas.append(f"VALOR TOTAL DEL INVENTARIO (ya calculado): ${total:,.2f}")
    lineas.append(f"PRODUCTOS EN O BAJO SU MÍNIMO: {', '.join(bajos) or 'ninguno'}")
    lineas.append(f"LISTA DE COMPRAS SUGERIDA (urgentes; perecederos para pocos días, lo demás para 1 semana): {'; '.join(compras) or 'nada urgente'}")
    return "\n".join(lineas)


def preguntar_a_gemini(texto: str | None = None, audio: bytes | None = None, mime: str | None = None) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(500, "Falta la variable de entorno GEMINI_API_KEY")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    partes = [PROMPT.format(inventario=texto_inventario())]
    if audio:
        partes.append(types.Part.from_bytes(data=audio, mime_type=mime or "audio/webm"))
        partes.append("Interpreta el audio anterior.")
    if texto:
        partes.append(f'El usuario escribió: "{texto}"')

    r = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=partes,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
    )
    try:
        return json.loads(r.text)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(502, f"La IA no devolvió JSON válido: {r.text!r}")


def procesar(resultado_ia: dict, texto_original: str) -> dict:
    acciones = resultado_ia.get("acciones") or []
    quiere_lista = any((a.get("tipo") or "").lower() == "enviar_lista" for a in acciones)
    aplicadas = aplicar_acciones(acciones, texto_original)
    respuesta = resultado_ia.get("respuesta", "")
    fallidas = [a for a in aplicadas if not a["ok"]]
    if fallidas:
        # La IA respondió antes de aplicar; si algo falló, decimos la verdad
        respuesta = "Ojo, no pude registrar todo. " + " ".join(
            f"{a['producto']}: {a['error']}." for a in fallidas
        ) + " ¿Me lo repites?"
    return {
        "transcripcion": resultado_ia.get("transcripcion", texto_original),
        "respuesta": respuesta,
        "acciones": aplicadas,
        "inventario": listar_productos(),
        "whatsapp_url": armar_lista_compras()["whatsapp_url"] if quiere_lista else None,
    }


# ---------------------------------------------------------------- Endpoints
class Texto(BaseModel):
    texto: str


@app.post("/api/voz")
async def voz(audio: UploadFile = File(...)):
    datos = await audio.read()
    if not datos:
        raise HTTPException(400, "Audio vacío")
    mime = (audio.content_type or "audio/webm").split(";")[0]
    ia = preguntar_a_gemini(audio=datos, mime=mime)
    return procesar(ia, ia.get("transcripcion", "(audio)"))


@app.post("/api/texto")
def texto(body: Texto):
    ia = preguntar_a_gemini(texto=body.texto)
    return procesar(ia, body.texto)


@app.get("/api/inventario")
def inventario():
    return listar_productos()


@app.get("/api/prediccion")
def prediccion():
    """Por producto: venta diaria, días restantes, cuándo se acaba, cuánto comprar y urgencia."""
    return calcular_prediccion()


def armar_lista_compras(todas: bool = False) -> dict:
    """Lista de compras a partir de la predicción + mensaje listo para WhatsApp."""
    items = [
        {"nombre": p["nombre"], "cantidad": p["comprar"], "unidad": p["unidad"],
         "categoria": p["categoria"], "urgencia": p["urgencia"], "se_acaba": p["se_acaba_texto"],
         "costo_estimado": round(p["comprar"] * (p["precio"] or 0), 2)}
        for p in calcular_prediccion()
        if p["comprar"] > 0 and (todas or p["urgencia"] in ("alta", "media"))
    ]
    lineas = ["🛒 *Pedido de surtido*", f"📅 {datetime.now():%d/%m/%Y}", ""]
    for i in items:
        unidad = "kg" if i["unidad"] == "kg" else "pzas"
        lineas.append(f"• {i['cantidad']:g} {unidad} — {i['nombre']}")
    lineas += ["", "Enviado con Surtí 🤖"]
    mensaje = "\n".join(lineas)
    return {
        "items": items,
        "total_estimado": round(sum(i["costo_estimado"] for i in items), 2),
        "mensaje": mensaje,
        "whatsapp_url": "https://wa.me/?text=" + quote(mensaje),
    }


@app.get("/api/lista-compras")
def lista_compras(todas: bool = False):
    """Qué comprar y cuánto (urgentes por defecto; ?todas=true incluye todo lo sugerido)."""
    return armar_lista_compras(todas)


def mapear_columnas_con_ia(encabezados: list, muestra: list) -> dict | None:
    """Gemini decide qué columna del Excel es cada dato. Devuelve None si no hay IA disponible."""
    if not os.getenv("GEMINI_API_KEY"):
        return None
    from google import genai
    from google.genai import types

    tabla = "\n".join(
        " | ".join(f"[{i}] {'' if v is None else v}" for i, v in enumerate(fila)) for fila in muestra
    )
    prompt = f"""Este es el inventario en Excel de una tienda pequeña en México.
Encabezados (con su índice): {json.dumps({i: h for i, h in enumerate(encabezados)}, ensure_ascii=False)}
Primeras filas:
{tabla}

Di qué índice de columna corresponde a cada campo (o null si no existe):
- nombre: nombre/descripción del producto
- cantidad: existencia actual / cuántos hay
- unidad: unidad de medida (pieza, kg, litro)
- precio: precio de VENTA al público
- costo: precio de COMPRA / costo
- minimo: stock mínimo / punto de reorden
- categoria: categoría / departamento / familia
Responde SOLO JSON: {{"nombre": 0, "cantidad": 1, "unidad": null, "precio": 2, "costo": null, "minimo": null, "categoria": null}}"""
    try:
        cliente = genai.Client(api_key=os.environ["GEMINI_API_KEY"])  # en variable: si no, se cierra antes de usarse
        r = cliente.models.generate_content(
            model=GEMINI_MODEL, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
        )
        crudo = json.loads(r.text)
        mapa = {k: int(v) for k, v in crudo.items()
                if k in importar.CAMPOS and isinstance(v, (int, float)) and 0 <= int(v) < len(encabezados)}
        return mapa if "nombre" in mapa else None
    except Exception:
        return None


@app.post("/api/importar")
async def importar_excel(archivo: UploadFile = File(...), confirmar: bool = Form(False)):
    """Sube el Excel/CSV de la tienda. confirmar=false -> vista previa; confirmar=true -> guarda."""
    contenido = await archivo.read()
    try:
        encabezados, filas = importar.leer_tabla(contenido, archivo.filename or "")
    except ValueError as e:
        raise HTTPException(400, str(e))

    mapa = mapear_columnas_con_ia(encabezados, filas[:6])
    metodo = "ia"
    if not mapa:
        mapa, metodo = importar.mapear_heuristico(encabezados), "palabras clave"
    if "nombre" not in mapa:
        raise HTTPException(400, "No encontré la columna con el nombre de los productos")

    productos, ignoradas = importar.extraer_productos(filas, mapa)

    con = db()
    existentes = {normalizar(f["nombre"]): f for f in con.execute("SELECT * FROM productos").fetchall()}
    for p in productos:
        actual = existentes.get(normalizar(p["nombre"]))
        p["accion"] = "actualizar" if actual else "nuevo"
        p["antes"] = actual["cantidad"] if actual else None

    if confirmar:
        ahora = datetime.now().isoformat(timespec="seconds")
        for p in productos:
            actual = existentes.get(normalizar(p["nombre"]))
            if actual:
                con.execute(
                    "UPDATE productos SET cantidad=?, precio=COALESCE(?, precio), costo=COALESCE(?, costo), "
                    "minimo=?, unidad=?, categoria=COALESCE(?, categoria) WHERE id=?",
                    (p["cantidad"], p["precio"], p["costo"], p["minimo"], p["unidad"], p["categoria"], actual["id"]),
                )
                pid, tipo = actual["id"], "ajuste"
            else:
                con.execute(
                    "INSERT INTO productos (nombre, unidad, cantidad, minimo, precio, categoria, costo) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (p["nombre"], p["unidad"], p["cantidad"], p["minimo"], p["precio"], p["categoria"], p["costo"]),
                )
                pid, tipo = con.execute("SELECT last_insert_rowid()").fetchone()[0], "alta"
            con.execute(
                "INSERT INTO movimientos (producto_id, tipo, cantidad, fecha, texto_original) VALUES (?,?,?,?,?)",
                (pid, tipo, p["cantidad"], ahora, f"(importado de {archivo.filename})"),
            )
        con.commit()
    con.close()

    return {
        "archivo": archivo.filename,
        "columnas": {campo: encabezados[i] for campo, i in mapa.items()},
        "metodo": metodo,
        "productos": productos,
        "nuevos": sum(p["accion"] == "nuevo" for p in productos),
        "actualizados": sum(p["accion"] == "actualizar" for p in productos),
        "ignoradas": ignoradas,
        "guardado": confirmar,
    }


@app.get("/api/alertas")
def alertas():
    return [p for p in listar_productos() if p["estado"] in ("bajo", "agotado")]


@app.get("/api/movimientos")
def movimientos(limite: int = 30):
    con = db()
    filas = con.execute(
        """SELECT m.*, p.nombre, p.unidad FROM movimientos m
           JOIN productos p ON p.id = m.producto_id ORDER BY m.id DESC LIMIT ?""",
        (limite,),
    ).fetchall()
    con.close()
    return [dict(f) for f in filas]


@app.get("/api/esp32")
def esp32():
    """Respuesta compacta para la pantalla OLED del ESP32."""
    prods = listar_productos()
    criticos = [p for p in prods if p["estado"] in ("bajo", "agotado")]
    atencion = [p for p in prods if p["estado"] == "atencion"]
    nivel = "rojo" if criticos else ("amarillo" if atencion else "verde")
    lineas = [f"{p['nombre'][:13]} {p['cantidad']:g}" for p in criticos[:4]]
    ultimo = movimientos(1)
    return {
        "nivel": nivel,
        "criticos": len(criticos),
        "lineas": lineas,
        "ultimo": (f"{ultimo[0]['tipo']}: {ultimo[0]['nombre'][:12]}" if ultimo else ""),
        "ultimo_id": ultimo[0]["id"] if ultimo else 0,
    }


@app.post("/api/reset")
def reset():
    """Reinicia el inventario de demostración (útil antes de presentar)."""
    init_db(reset=True)
    return {"ok": True}


# Servir la app web
app.mount("/static", StaticFiles(directory=APP_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(APP_DIR / "index.html")
