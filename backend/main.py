"""
Backend del asistente de inventario por voz.

Ejecutar (desde la carpeta backend):
    pip install -r requirements.txt
    set GEMINI_API_KEY=tu_clave        (PowerShell: $env:GEMINI_API_KEY="tu_clave")
    python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Abrir: http://localhost:8000
"""
import csv
import difflib
import io
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
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import cfdi
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
# Modelo estable y disponible para esta clave (gemini-2.5-flash ya no está disponible para cuentas nuevas).
# Se puede cambiar en backend/.env con GEMINI_MODEL=...
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"

app = FastAPI(title="STOCK — Inventario por voz")
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
    ("Café Nescafé 42 g", "pieza", 8, 2, 42, "Abarrotes", 0.25),
    ("Ate de membrillo", "pieza", 9, 2, 35, "Dulces", 0.2),
    ("Papel higiénico 4 rollos", "pieza", 8, 4, 38, "Limpieza", 0.6),
    ("Jabón Zote", "pieza", 14, 4, 22, "Limpieza", 0.35),
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
        con.executescript(
            "DROP TABLE IF EXISTS movimientos; DROP TABLE IF EXISTS productos; DROP TABLE IF EXISTS cfdi_procesados;"
        )
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
        -- Facturas de proveedor ya cargadas (evita sumar dos veces la misma)
        CREATE TABLE IF NOT EXISTS cfdi_procesados (
            uuid TEXT PRIMARY KEY,
            proveedor TEXT,
            total REAL,
            forma_pago TEXT,
            fecha TEXT NOT NULL,
            archivo TEXT
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
        valor = round(p["cantidad"] * (p["precio"] or 0), 2)
        if not v or not v["total"]:
            urg = "alta" if p["estado"] in ("bajo", "agotado") else "baja"
            resultado.append({**p, "venta_diaria": 0, "dias_restantes": None, "se_acaba": None,
                              "se_acaba_texto": "sin ventas recientes", "comprar": 0, "urgencia": urg,
                              "valor_actual": valor, "baja_rotacion": p["cantidad"] > p["minimo"] and valor > 0})
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
            "valor_actual": valor,
            # Dinero congelado: alcanza para 2+ semanas y hay más del mínimo -> no conviene resurtir
            "baja_rotacion": (dias is None or dias >= 14) and p["cantidad"] > p["minimo"],
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
                resultados.append({"producto": nombre, "tipo": "alta", "cantidad": cantidad,
                                   "unidad": a.get("unidad") or "pieza", "ok": True})
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
PROMPT = """Eres "STOCK", el asistente de inventario por voz de una tiendita en Durango, México.
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
- "¿Qué surto y qué NO?" / "¿qué no debo pedir?" -> di lo urgente con cantidades, cuánto EFECTIVO APARTAR, y advierte
  qué productos de BAJA ROTACIÓN no conviene comprarle al preventista (tienen dinero congelado).
- Si recibes una FOTO de ticket o nota de proveedor: cada producto que llegó es una acción "entrada"
  (usa el nombre del inventario si ya existe; si no existe, ponlo tal cual y se dará de alta). En "respuesta" resume qué sumaste.
- Si recibes una FOTO de anaquel: cuenta las piezas visibles de productos del inventario y regístralas como "ajuste".
- Si la imagen no se entiende, no inventes acciones: pide otra foto más clara.
- "respuesta": frase corta, amable y hablada (se leerá en voz alta), en español de México (trata de "tú": "vendes", "tienes"; nunca "vos" ni "vendés"). Confirma lo que hiciste
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
        f"{' | BAJA ROTACIÓN (NO RESURTIR)' if p['baja_rotacion'] else ''}"
        for p in prods
    ]
    lentos = [f"{p['nombre']} (${p['valor_actual']:,.0f} congelados)" for p in prods if p["baja_rotacion"]]
    urgentes = [p for p in prods if p["comprar"] > 0 and p["urgencia"] in ("alta", "media")]
    apartar = sum(p["comprar"] * (p["precio"] or 0) for p in urgentes)
    total = sum(p["cantidad"] * (p["precio"] or 0) for p in prods)
    bajos = [p["nombre"] for p in prods if p["estado"] in ("bajo", "agotado")]
    compras = [f"{p['comprar']:g} {p['unidad']} de {p['nombre']}" for p in prods
               if p["urgencia"] in ("alta", "media") and p["comprar"] > 0]
    ahora = datetime.now()
    lineas.append(f"\nHOY ES {DIAS_SEMANA[ahora.weekday()].upper()} {ahora:%d/%m/%Y} {ahora:%H:%M}")
    lineas.append(f"VALOR TOTAL DEL INVENTARIO (ya calculado): ${total:,.2f}")
    lineas.append(f"PRODUCTOS EN O BAJO SU MÍNIMO: {', '.join(bajos) or 'ninguno'}")
    lineas.append(f"EFECTIVO A APARTAR PARA SURTIDO URGENTE (ya calculado): ${apartar:,.0f}")
    lineas.append(f"BAJA ROTACIÓN / DINERO CONGELADO (NO PEDIR): {', '.join(lentos) or 'ninguno'}")
    lineas.append(f"LISTA DE COMPRAS SUGERIDA (urgentes; perecederos para pocos días, lo demás para 1 semana): {'; '.join(compras) or 'nada urgente'}")
    return "\n".join(lineas)


INSTRUCCION_FOTO = {
    "ticket": "Esta imagen es un ticket o nota de proveedor: lo que aparece LLEGÓ a la tienda. "
              "Cada producto es una acción 'entrada' con su cantidad. En 'transcripcion' resume el ticket.",
    "anaquel": "Esta imagen es un anaquel o refrigerador de la tienda: cuenta las piezas visibles de productos "
               "del inventario y regístralas como 'ajuste'. En 'transcripcion' di qué contaste.",
    "factura": "Este documento es una FACTURA de un proveedor: todo lo que trae LLEGÓ a la tienda. "
               + "Cada partida es una acción 'entrada'. " + "{conversion}"
               + " Agrega también al JSON la llave \"factura\": {{\"proveedor\": \"...\", \"total\": 0, "
               "\"uuid\": \"folio fiscal si aparece o null\", \"forma_pago\": \"clave de 2 dígitos si aparece o null\"}}. "
               "En 'transcripcion' resume la factura (proveedor y cuántas partidas).",
}

# Cómo convertir lo que vende el proveedor (mayoreo) a lo que cuenta la tienda (piezas o kilos)
REGLAS_CONVERSION = (
    "IMPORTANTE: el proveedor vende por mayoreo. Convierte a la UNIDAD DEL INVENTARIO de la tienda: "
    "'CAJA C/24' = 24 piezas por caja, 'PAQ C/6' = 6 piezas por paquete, 'BULTO 10 KG' = 10 kg por bulto, "
    "'CHAROLA C/30' = 30 piezas. Multiplica por la cantidad de cajas/paquetes. Ejemplo: 2 cajas C/24 = 48 piezas. "
    "Usa el nombre EXACTO del inventario si el producto ya existe; si no existe, ponle un nombre corto y claro "
    "(sin claves del proveedor) y su unidad (pieza o kg). En cada acción agrega \"partida\" con el número de partida (1, 2, 3...)."
)
INSTRUCCION_FOTO["factura"] = INSTRUCCION_FOTO["factura"].format(conversion=REGLAS_CONVERSION)


def preguntar_a_gemini(texto: str | None = None, audio: bytes | None = None, mime: str | None = None,
                       imagen: bytes | None = None, modo_foto: str = "ticket") -> dict:
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
    if imagen:
        partes.append(types.Part.from_bytes(data=imagen, mime_type=mime or "image/jpeg"))
        partes.append(INSTRUCCION_FOTO.get(modo_foto, INSTRUCCION_FOTO["ticket"]))
    if texto:
        partes.append(f'El usuario escribió: "{texto}"')

    ultimo = ""
    for _intento in range(2):  # si la IA responde mal, se reintenta una vez
        r = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=partes,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
        )
        ultimo = r.text or ""
        resultado = leer_json(ultimo)
        if resultado is not None:
            return resultado
    raise HTTPException(502, "No entendí bien, ¿me lo repites?")


def leer_json(texto: str):
    """Lee el primer objeto JSON del texto, aunque la IA agregue basura antes o después."""
    texto = (texto or "").strip()
    inicio = texto.find("{")
    if inicio < 0:
        return None
    try:
        obj, _fin = json.JSONDecoder().raw_decode(texto[inicio:])
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


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
    fecha = f"📅 {datetime.now():%d/%m/%Y}"
    linea = lambda i: f"• {i['cantidad']:g} {'kg' if i['unidad'] == 'kg' else 'pzas'} — {i['nombre']}"  # noqa: E731

    # Agrupado por categoría (cada categoría suele tener su propio proveedor: Coca, Bimbo, Lala, tortillería...)
    grupos: dict[str, list] = {}
    for i in items:
        grupos.setdefault(i["categoria"] or "General", []).append(i)
    por_proveedor, lineas = [], ["🛒 *Pedido de surtido*", fecha, ""]
    for proveedor in sorted(grupos):
        lista_p = grupos[proveedor]
        msg_p = "\n".join([f"🛒 *Pedido — {proveedor}*", fecha, "", *map(linea, lista_p), "", "Enviado con STOCK 📦"])
        por_proveedor.append({
            "proveedor": proveedor,
            "items": lista_p,
            "subtotal_estimado": round(sum(i["costo_estimado"] for i in lista_p), 2),
            "whatsapp_url": "https://wa.me/?text=" + quote(msg_p),
        })
        lineas += [f"*{proveedor}:*", *map(linea, lista_p), ""]
    lineas.append("Enviado con STOCK 📦")
    mensaje = "\n".join(lineas)
    return {
        "items": items,
        "por_proveedor": por_proveedor,
        "total_estimado": round(sum(i["costo_estimado"] for i in items), 2),
        "mensaje": mensaje,
        "whatsapp_url": "https://wa.me/?text=" + quote(mensaje),
    }


def calcular_resumen(pred: list | None = None, lista: dict | None = None) -> dict:
    """KPIs de dinero para el tablero: valor, efectivo a apartar y capital congelado."""
    pred = pred if pred is not None else calcular_prediccion()
    lista = lista if lista is not None else armar_lista_compras(False)
    lentos = [p for p in pred if p["baja_rotacion"]]
    criticos = [p for p in pred if p["estado"] in ("bajo", "agotado")]
    return {
        "valor_inventario": round(sum(p["valor_actual"] for p in pred), 2),
        "efectivo_apartar": lista["total_estimado"],
        "capital_congelado": round(sum(p["valor_actual"] for p in lentos), 2),
        "productos_criticos": len(criticos),
        "productos_lentos": len(lentos),
        "urgentes_lista": len(lista["items"]),
        "salud_porcentaje": round((len(pred) - len(criticos)) / max(1, len(pred)) * 100),
        "no_pedir": lentos,
    }


@app.get("/api/resumen")
def resumen():
    return calcular_resumen()


@app.get("/api/tablero")
def tablero(todas: bool = False, limite_movimientos: int = 15):
    """Todo lo que pinta la pantalla principal en una sola llamada."""
    pred = calcular_prediccion()
    urgentes = armar_lista_compras(False)
    return {
        "prediccion": pred,
        "resumen": calcular_resumen(pred, urgentes),
        "lista": armar_lista_compras(True) if todas else urgentes,
        "movimientos": movimientos(limite_movimientos),
    }


@app.post("/api/foto")
async def foto(imagen: UploadFile = File(...), modo: str = Form("ticket")):
    """Foto de ticket de proveedor (suma lo que llegó) o de anaquel (ajusta lo que se ve)."""
    datos = await imagen.read()
    if not datos:
        raise HTTPException(400, "Imagen vacía")
    if len(datos) > 15 * 1024 * 1024:
        raise HTTPException(400, "La foto es muy pesada (máx. 15 MB)")
    mime = (imagen.content_type or "image/jpeg").split(";")[0]
    modo = modo if modo in INSTRUCCION_FOTO else "ticket"
    ia = preguntar_a_gemini(imagen=datos, mime=mime, modo_foto=modo)
    return procesar(ia, f"(foto de {modo})")


class AjusteRapido(BaseModel):
    producto_id: int
    delta: float


@app.post("/api/ajuste-rapido")
def ajuste_rapido(body: AjusteRapido):
    """Botones − / + del inventario: − registra una venta, + una entrada. Sin IA."""
    con = db()
    p = con.execute("SELECT * FROM productos WHERE id=?", (body.producto_id,)).fetchone()
    con.close()
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    tipo = "venta" if body.delta < 0 else "entrada"
    resultado = aplicar_acciones([{"tipo": tipo, "producto": p["nombre"], "cantidad": abs(body.delta)}],
                                 "(ajuste rápido)")
    if resultado and not resultado[0]["ok"]:
        raise HTTPException(400, resultado[0]["error"])
    return {"acciones": resultado}


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


# ---------------------------------------------------------------- Facturas de proveedor (CFDI XML / PDF)
DEMO_CFDI = BASE_DIR / "demo_cfdi.xml"
MSG_FACTURA_REPETIDA = ("Esta factura ya la subiste antes; no la volvimos a sumar "
                        "para no duplicar tu inventario.")
LIMITE_EFECTIVO_TIP = 2000


def _factura_ya_cargada(uuid: str) -> bool:
    con = db()
    existe = con.execute("SELECT 1 FROM cfdi_procesados WHERE uuid=?", (uuid,)).fetchone() is not None
    con.close()
    return existe


def _guardar_factura(uuid: str, proveedor: str, total: float, forma_pago: str | None, archivo: str):
    con = db()
    con.execute(
        "INSERT INTO cfdi_procesados (uuid, proveedor, total, forma_pago, fecha, archivo) VALUES (?,?,?,?,?,?)",
        (uuid, proveedor, total, forma_pago, datetime.now().isoformat(timespec="seconds"), archivo),
    )
    con.commit()
    con.close()


def _solo_entradas(ia: dict) -> dict:
    """Todo lo que viene en una factura LLEGÓ a la tienda: se registra como entrada."""
    for a in ia.get("acciones") or []:
        if (a.get("tipo") or "").lower() not in ("entrada", "alta"):
            a["tipo"] = "entrada"
    return ia


def _tip_efectivo(forma_pago: str | None, total: float) -> str | None:
    if str(forma_pago or "").strip() == "01" and total > LIMITE_EFECTIVO_TIP:
        return (f"💡 Tip: como esta compra pasó de ${LIMITE_EFECTIVO_TIP:,} en efectivo, si la próxima la pagas "
                "por transferencia te sirve mejor si llevas cuentas con contador.")
    return None


def _costos_y_tips(acciones: list, importes: dict) -> list:
    """Guarda cuánto te costó cada pieza/kilo y avisa (amable) si un producto llegó más caro que la vez pasada."""
    tips = []
    con = db()
    for a in acciones:
        partida, cantidad = a.get("partida"), float(a.get("cantidad") or 0)
        try:
            importe = importes.get(int(partida))
        except (TypeError, ValueError):
            importe = None
        if not importe or cantidad <= 0:
            continue
        p = buscar_producto(con, a.get("producto") or "")
        if not p:
            continue
        costo_nuevo = round(importe / cantidad, 2)
        if p["costo"] and costo_nuevo > p["costo"] * 1.03 and len(tips) < 2:
            tips.append(f"💡 Ojo: {p['nombre']} te llegó más caro que la vez pasada "
                        f"(${p['costo']:,.2f} → ${costo_nuevo:,.2f} por {p['unidad']}). "
                        "Revisa si conviene ajustar tu precio.")
        con.execute("UPDATE productos SET costo=? WHERE id=?", (costo_nuevo, p["id"]))
    con.commit()
    con.close()
    return tips


def procesar_factura_xml(contenido: bytes, nombre_archivo: str) -> dict:
    try:
        f = cfdi.leer_cfdi(contenido)
    except ValueError as e:
        raise HTTPException(400, f"No pude leer la factura: {e}")
    if _factura_ya_cargada(f["uuid"]):
        raise HTTPException(409, MSG_FACTURA_REPETIDA)

    instruccion = (
        f"{REGLAS_CONVERSION}\n\n{cfdi.partidas_para_ia(f)}\n\n"
        "Todo esto LLEGÓ a la tienda: registra cada partida como 'entrada' en piezas o kilos. "
        "En 'respuesta' di en una frase qué sumaste (ej. 'Sumé 72 Cocas, 12 leches y 10 kilos de frijol')."
    )
    ia = _solo_entradas(preguntar_a_gemini(texto=instruccion))
    acciones_ia = [dict(a) for a in ia.get("acciones") or []]
    resultado = procesar(ia, f"(factura de {f['proveedor']})")
    if not any(a["ok"] for a in resultado["acciones"]):
        return resultado  # no se sumó nada: no la marcamos como cargada para que pueda reintentarse

    tips = _costos_y_tips(acciones_ia, {c["partida"]: c["importe"] for c in f["conceptos"]})
    tip = _tip_efectivo(f["forma_pago"], f["total"])
    if tip:
        tips.append(tip)
    if tips:
        resultado["respuesta"] = f"{resultado['respuesta']} {' '.join(tips)}"
    _guardar_factura(f["uuid"], f["proveedor"], f["total"], f["forma_pago"], nombre_archivo)
    resultado["factura"] = {"uuid": f["uuid"], "proveedor": f["proveedor"], "total": f["total"],
                            "forma_pago": f["forma_pago"], "partidas": len(f["conceptos"]), "tipo": "xml"}
    return resultado


def procesar_factura_pdf(contenido: bytes, nombre_archivo: str) -> dict:
    ia = _solo_entradas(preguntar_a_gemini(imagen=contenido, mime="application/pdf", modo_foto="factura"))
    info = ia.get("factura") if isinstance(ia.get("factura"), dict) else {}
    uuid = str(info.get("uuid") or "").strip().upper()
    if len(uuid) < 30:  # sin folio fiscal legible: identificador por archivo y hora
        uuid = f"PDF-{nombre_archivo}-{datetime.now():%Y%m%d%H%M%S}"
    elif _factura_ya_cargada(uuid):
        raise HTTPException(409, MSG_FACTURA_REPETIDA)

    proveedor = str(info.get("proveedor") or "Proveedor")
    try:
        total = float(info.get("total") or 0)
    except (TypeError, ValueError):
        total = 0.0
    forma_pago = (str(info.get("forma_pago")).zfill(2) if info.get("forma_pago") else None)

    resultado = procesar(ia, f"(factura PDF de {proveedor})")
    if not any(a["ok"] for a in resultado["acciones"]):
        return resultado
    tip = _tip_efectivo(forma_pago, total)
    if tip:
        resultado["respuesta"] = f"{resultado['respuesta']} {tip}"
    _guardar_factura(uuid, proveedor, total, forma_pago, nombre_archivo)
    resultado["factura"] = {"uuid": uuid, "proveedor": proveedor, "total": total, "forma_pago": forma_pago,
                            "partidas": len(resultado["acciones"]), "tipo": "pdf"}
    return resultado


@app.post("/api/cfdi")
async def subir_factura(archivo: UploadFile = File(...)):
    """Sube la factura del proveedor (XML o PDF): suma lo que llegó al inventario, convirtiendo cajas a piezas."""
    contenido = await archivo.read()
    nombre = archivo.filename or "factura"
    if not contenido:
        raise HTTPException(400, "El archivo está vacío")
    if len(contenido) > 15 * 1024 * 1024:
        raise HTTPException(400, "El archivo es muy pesado (máx. 15 MB)")
    if contenido.lstrip()[:5] == b"%PDF-" or nombre.lower().endswith(".pdf"):
        return procesar_factura_pdf(contenido, nombre)
    if contenido.lstrip()[:1] == b"<" or nombre.lower().endswith(".xml"):
        return procesar_factura_xml(contenido, nombre)
    raise HTTPException(400, "Sube el XML o el PDF de tu factura")


@app.post("/api/cfdi/demo")
def factura_demo():
    """Procesa la factura de ejemplo (backend/demo_cfdi.xml) con un clic, para la demo."""
    return procesar_factura_xml(DEMO_CFDI.read_bytes(), DEMO_CFDI.name)


# ---------------------------------------------------------------- Resumen del mes (sin lenguaje contable)
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def calcular_resumen_mes() -> dict:
    ahora = datetime.now()
    inicio = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    con = db()
    ventas = con.execute(
        "SELECT p.nombre, p.unidad, SUM(m.cantidad) AS cantidad, SUM(m.cantidad * COALESCE(p.precio, 0)) AS monto, "
        "COUNT(*) AS veces FROM movimientos m JOIN productos p ON p.id = m.producto_id "
        "WHERE m.tipo='venta' AND m.fecha >= ? GROUP BY p.id ORDER BY monto DESC",
        (inicio,),
    ).fetchall()
    facturas = con.execute(
        "SELECT * FROM cfdi_procesados WHERE fecha >= ? ORDER BY fecha DESC", (inicio,)
    ).fetchall()
    con.close()

    parado = calcular_resumen()["no_pedir"]
    return {
        "mes": f"{MESES[ahora.month - 1]} {ahora.year}",
        "vendido": {
            "monto": round(sum(v["monto"] for v in ventas), 2),
            "movimientos": sum(v["veces"] for v in ventas),
        },
        "surtido": {
            "facturas": len(facturas),
            "monto": round(sum(f["total"] or 0 for f in facturas), 2),
        },
        "mas_vendidos": [
            {"nombre": v["nombre"], "cantidad": round(v["cantidad"], 2), "unidad": v["unidad"], "monto": round(v["monto"], 2)}
            for v in ventas[:5]
        ],
        "dinero_parado": {
            "monto": round(sum(p["valor_actual"] for p in parado), 2),
            "productos": [{"nombre": p["nombre"], "cantidad": p["cantidad"], "unidad": p["unidad"],
                           "valor": p["valor_actual"], "se_acaba": p["se_acaba_texto"]} for p in parado],
        },
        "ultimas_facturas": [
            {"fecha": f["fecha"], "proveedor": f["proveedor"], "total": f["total"], "archivo": f["archivo"]}
            for f in facturas[:5]
        ],
        "todas_las_facturas": [dict(f) for f in facturas],
    }


@app.get("/api/resumen-mes")
def resumen_mes():
    """Tu mes en resumen: lo vendido, lo surtido con facturas y el dinero parado."""
    datos = calcular_resumen_mes()
    datos.pop("todas_las_facturas")
    return datos


@app.get("/api/resumen-mes/csv")
def resumen_mes_csv():
    """Archivo para guardar o mandar al contador: facturas cargadas y movimientos del mes."""
    d = calcular_resumen_mes()
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow([f"Resumen del mes - {d['mes']}", "", "Generado con STOCK", datetime.now().strftime("%d/%m/%Y %H:%M")])
    w.writerow([])
    w.writerow(["Lo que has vendido (registrado en la app)", f"{d['vendido']['monto']:.2f}",
                f"{d['vendido']['movimientos']} ventas registradas"])
    w.writerow(["Lo que has surtido con facturas", f"{d['surtido']['monto']:.2f}",
                f"{d['surtido']['facturas']} facturas"])
    w.writerow(["Dinero parado (productos que casi no salen)", f"{d['dinero_parado']['monto']:.2f}",
                f"{len(d['dinero_parado']['productos'])} productos"])
    w.writerow([])
    w.writerow(["FACTURAS DE PROVEEDOR CARGADAS"])
    w.writerow(["Fecha de carga", "Proveedor", "Total", "Forma de pago", "Folio", "Archivo"])
    for f in d["todas_las_facturas"]:
        w.writerow([f["fecha"].replace("T", " "), f["proveedor"], f"{(f['total'] or 0):.2f}",
                    f["forma_pago"] or "", f["uuid"], f["archivo"] or ""])
    w.writerow([])
    w.writerow(["LO QUE MÁS SE VENDIÓ"])
    w.writerow(["Producto", "Cantidad", "Unidad", "Monto aproximado"])
    for v in d["mas_vendidos"]:
        w.writerow([v["nombre"], f"{v['cantidad']:g}", v["unidad"], f"{v['monto']:.2f}"])
    w.writerow([])
    w.writerow(["DINERO PARADO (EVITA VOLVER A PEDIRLOS)"])
    w.writerow(["Producto", "Cantidad", "Unidad", "Valor", "Se acaba"])
    for p in d["dinero_parado"]["productos"]:
        w.writerow([p["nombre"], f"{p['cantidad']:g}", p["unidad"], f"{p['valor']:.2f}", p["se_acaba"]])
    return Response(
        content=("﻿" + salida.getvalue()).encode("utf-8"),  # BOM: Excel abre bien los acentos
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="resumen_mensual_stock.csv"'},
    )


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


@app.post("/api/reset")
def reset():
    """Reinicia el inventario de demostración (útil antes de presentar)."""
    init_db(reset=True)
    return {"ok": True}


# Servir la app web
app.mount("/static", StaticFiles(directory=APP_DIR), name="static")


@app.get("/")
def portada():
    """Portada de STOCK (landing)."""
    return FileResponse(APP_DIR / "inicio.html")


@app.get("/app")
def aplicacion():
    """La app de inventario."""
    return FileResponse(APP_DIR / "index.html")


@app.get("/clasico")
def clasico():
    """Interfaz anterior (respaldo)."""
    return FileResponse(APP_DIR / "clasico.html")
