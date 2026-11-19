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
import os
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
    # nombre, unidad, cantidad, minimo, precio, categoria
    ("Coca-Cola 600 ml", "pieza", 24, 12, 22, "Bebidas"),
    ("Sabritas sal 45 g", "pieza", 15, 10, 20, "Botanas"),
    ("Huevo", "kg", 4, 3, 48, "Básicos"),
    ("Frijol pinto", "kg", 12, 5, 32, "Granel"),
    ("Arroz", "kg", 8, 5, 28, "Granel"),
    ("Leche Lala 1 L", "pieza", 6, 8, 29, "Lácteos"),
    ("Pan Bimbo grande", "pieza", 3, 4, 52, "Panadería"),
    ("Tortillas", "kg", 5, 3, 24, "Básicos"),
]


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
            categoria TEXT
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
    if con.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
        con.executemany(
            "INSERT INTO productos (nombre, unidad, cantidad, minimo, precio, categoria) VALUES (?,?,?,?,?,?)",
            PRODUCTOS_DEMO,
        )
    con.commit()
    con.close()


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

Reglas:
- Usa EXACTAMENTE el nombre del inventario si el producto ya existe ("coca" -> "Coca-Cola 600 ml").
- Convierte cantidades: "una docena" = 12, "medio kilo" = 0.5, "un cartón de huevo" = 30 piezas o ~1.8 kg según la unidad del producto.
- IMPORTANTE: "cantidad" SIEMPRE va en la unidad del producto en el inventario. Si el producto está en kg y te dicen
  piezas o docenas, convierte a kg (1 huevo ≈ 0.06 kg, 1 docena de huevo ≈ 0.72 kg).
- Si dice cajas/paquetes y no sabes cuántas piezas trae, pregunta en "respuesta" y no inventes la acción.
- Para cambiar precio usa tipo "precio" y pon el precio nuevo en "precio".
- NO hagas sumas ni multiplicaciones tú: usa el VALOR TOTAL y los valores ya calculados del inventario.
- "respuesta": frase corta, amable y hablada (se leerá en voz alta), en español de México. Confirma lo que hiciste
  y, si algún producto queda en o bajo su mínimo, avísale. Para consultas, responde con los datos del inventario.
- "transcripcion": lo que entendiste que dijo el usuario.

Formato EXACTO:
{{"transcripcion": "...", "acciones": [{{"tipo": "...", "producto": "...", "cantidad": 0, "unidad": "...", "precio": null}}], "respuesta": "..."}}
"""


def texto_inventario() -> str:
    """Inventario para la IA, con los cálculos ya hechos (la IA no debe sumar)."""
    prods = listar_productos()
    lineas = [
        f"- {p['nombre']} | {p['unidad']} | {p['cantidad']:g} | {p['minimo']:g} | {p['precio']} "
        f"| valor ${(p['cantidad'] * (p['precio'] or 0)):,.2f} | estado: {p['estado']}"
        for p in prods
    ]
    total = sum(p["cantidad"] * (p["precio"] or 0) for p in prods)
    bajos = [p["nombre"] for p in prods if p["estado"] in ("bajo", "agotado")]
    lineas.append(f"\nVALOR TOTAL DEL INVENTARIO (ya calculado): ${total:,.2f}")
    lineas.append(f"PRODUCTOS EN O BAJO SU MÍNIMO: {', '.join(bajos) or 'ninguno'}")
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
