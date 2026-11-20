"""
Base de datos de STOCK: Postgres (Supabase) en la nube o SQLite en la laptop, con la misma interfaz.

- Si existe la variable DATABASE_URL (postgresql://...), se usa Postgres con un pool de conexiones.
- Si no, se usa el archivo local backend/inventario.db (desarrollo y pruebas).

El resto del código escribe SQL con placeholders "?" (siempre parametrizado) y aquí se traduce a "%s"
para Postgres. Ninguna consulta arma SQL con datos del usuario.
"""
import os
import sqlite3
from pathlib import Path

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
ES_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = Path(__file__).resolve().parent / "inventario.db"

_pool = None


def _pool_postgres():
    """Pool perezoso: se crea la primera vez que se necesita."""
    global _pool
    if _pool is None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=int(os.getenv("DB_POOL_MAX") or 5),
            # prepare_threshold=None: compatible con el pooler de Supabase (Supavisor)
            kwargs={"row_factory": dict_row, "prepare_threshold": None, "connect_timeout": 10},
            open=True,
        )
    return _pool


class Conexion:
    """Envoltura mínima: execute / insertar / ejecutar_varios / commit / rollback / close."""

    def __init__(self):
        self.es_postgres = ES_POSTGRES
        if ES_POSTGRES:
            self._con = _pool_postgres().getconn()
        else:
            self._con = sqlite3.connect(SQLITE_PATH)
            self._con.row_factory = sqlite3.Row

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.es_postgres else sql

    def execute(self, sql: str, params=()):
        return self._con.execute(self._sql(sql), tuple(params))

    def insertar(self, sql: str, params=()) -> int:
        """INSERT que regresa el id nuevo (RETURNING en Postgres, lastrowid en SQLite)."""
        if self.es_postgres:
            return self._con.execute(self._sql(sql) + " RETURNING id", tuple(params)).fetchone()["id"]
        return self._con.execute(sql, tuple(params)).lastrowid

    def ejecutar_varios(self, sql: str, filas: list):
        if not filas:
            return
        if self.es_postgres:
            with self._con.cursor() as cur:
                cur.executemany(self._sql(sql), filas)
        else:
            self._con.executemany(sql, filas)

    def script(self, sql: str):
        """Varias sentencias separadas por ';' (solo DDL fijo del código)."""
        if self.es_postgres:
            for sentencia in (s.strip() for s in sql.split(";")):
                if sentencia:
                    self._con.execute(sentencia)
        else:
            self._con.executescript(sql)

    def iniciar_escritura(self):
        """Toma el candado de escritura desde el inicio (SQLite). En Postgres se usa SELECT ... FOR UPDATE."""
        if not self.es_postgres:
            self._con.execute("BEGIN IMMEDIATE")

    @property
    def para_actualizar(self) -> str:
        return " FOR UPDATE" if self.es_postgres else ""

    def commit(self):
        self._con.commit()

    def rollback(self):
        self._con.rollback()

    def close(self):
        if self.es_postgres:
            try:  # cierra la transacción de lectura antes de devolverla (sin esto el pool avisa en cada consulta)
                if not self._con.closed and self._con.info.transaction_status != 0:  # 0 = IDLE
                    self._con.rollback()
            except Exception:  # noqa: BLE001 - si la conexión se cayó, el pool la descarta
                pass
            _pool_postgres().putconn(self._con)
        else:
            self._con.close()


def db() -> Conexion:
    return Conexion()


# ---------------------------------------------------------------- Esquema
ESQUEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE NOT NULL,
    unidad TEXT NOT NULL DEFAULT 'pieza',
    cantidad REAL NOT NULL DEFAULT 0,
    minimo REAL NOT NULL DEFAULT 0,
    precio REAL,
    categoria TEXT,
    costo_compra REAL
);
CREATE TABLE IF NOT EXISTS movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER REFERENCES productos(id),
    tipo TEXT NOT NULL,
    cantidad REAL NOT NULL,
    fecha TEXT NOT NULL,
    texto_original TEXT,
    lote_id TEXT,
    antes REAL, despues REAL,
    creado_en_lote INTEGER DEFAULT 0,
    precio_antes REAL, costo_antes REAL, minimo_antes REAL, nombre_antes TEXT
);
CREATE TABLE IF NOT EXISTS lotes (
    id TEXT PRIMARY KEY, origen TEXT, descripcion TEXT, cfdi_uuid TEXT, fecha TEXT,
    revertido INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cfdi_procesados (
    uuid TEXT PRIMARY KEY, proveedor TEXT, total REAL, forma_pago TEXT, fecha TEXT NOT NULL, archivo TEXT
);
"""

# En Postgres: DOUBLE PRECISION (REAL sería de 4 bytes y perdería centavos) e identidades.
ESQUEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS productos (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL,
    unidad TEXT NOT NULL DEFAULT 'pieza',
    cantidad DOUBLE PRECISION NOT NULL DEFAULT 0,
    minimo DOUBLE PRECISION NOT NULL DEFAULT 0,
    precio DOUBLE PRECISION,
    categoria TEXT,
    costo_compra DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS movimientos (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    producto_id BIGINT REFERENCES productos(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    cantidad DOUBLE PRECISION NOT NULL,
    fecha TEXT NOT NULL,
    texto_original TEXT,
    lote_id TEXT,
    antes DOUBLE PRECISION, despues DOUBLE PRECISION,
    creado_en_lote INTEGER DEFAULT 0,
    precio_antes DOUBLE PRECISION, costo_antes DOUBLE PRECISION, minimo_antes DOUBLE PRECISION, nombre_antes TEXT
);
CREATE TABLE IF NOT EXISTS lotes (
    id TEXT PRIMARY KEY, origen TEXT, descripcion TEXT, cfdi_uuid TEXT, fecha TEXT,
    revertido INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cfdi_procesados (
    uuid TEXT PRIMARY KEY, proveedor TEXT, total DOUBLE PRECISION, forma_pago TEXT, fecha TEXT NOT NULL,
    archivo TEXT
);
ALTER TABLE productos ENABLE ROW LEVEL SECURITY;
ALTER TABLE movimientos ENABLE ROW LEVEL SECURITY;
ALTER TABLE lotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE cfdi_procesados ENABLE ROW LEVEL SECURITY
"""
# RLS activado sin políticas: la API pública de Supabase (anon key) no puede leer ni escribir estas tablas.
# El backend entra con el usuario de la base (dueño de las tablas), que no está sujeto a RLS.

COLUMNAS_MOVIMIENTOS = {  # agregadas en versiones posteriores (migración de bases SQLite anteriores)
    "lote_id": "TEXT", "antes": "REAL", "despues": "REAL", "creado_en_lote": "INTEGER DEFAULT 0",
    "precio_antes": "REAL", "costo_antes": "REAL", "minimo_antes": "REAL", "nombre_antes": "TEXT",
}

INDICES = """
CREATE INDEX IF NOT EXISTS idx_mov_lote ON movimientos(lote_id);
CREATE INDEX IF NOT EXISTS idx_mov_producto ON movimientos(producto_id);
CREATE INDEX IF NOT EXISTS idx_mov_tipo_fecha ON movimientos(tipo, fecha)
"""


def crear_esquema(con: Conexion, reset: bool = False):
    if reset:
        tablas = ["movimientos", "productos", "cfdi_procesados", "lotes"]
        sufijo = " CASCADE" if con.es_postgres else ""
        con.script(";".join(f"DROP TABLE IF EXISTS {t}{sufijo}" for t in tablas))  # nombres fijos
    con.script(ESQUEMA_POSTGRES if con.es_postgres else ESQUEMA_SQLITE)
    if not con.es_postgres:  # migración de bases locales creadas con versiones anteriores
        cols_prod = {c["name"] for c in con.execute("PRAGMA table_info(productos)").fetchall()}
        if "costo_compra" not in cols_prod:
            con.execute("ALTER TABLE productos ADD COLUMN costo_compra REAL")
            if "costo" in cols_prod:
                con.execute("UPDATE productos SET costo_compra = costo")
        cols_mov = {c["name"] for c in con.execute("PRAGMA table_info(movimientos)").fetchall()}
        for columna, tipo in COLUMNAS_MOVIMIENTOS.items():
            if columna not in cols_mov:
                con.execute(f"ALTER TABLE movimientos ADD COLUMN {columna} {tipo}")  # lista fija
    # Huella (SHA-256) del archivo de la factura: detecta el mismo archivo aunque la IA lea distinto el folio
    if con.es_postgres:
        con.execute("ALTER TABLE cfdi_procesados ADD COLUMN IF NOT EXISTS huella TEXT")
    elif "huella" not in {c["name"] for c in con.execute("PRAGMA table_info(cfdi_procesados)").fetchall()}:
        con.execute("ALTER TABLE cfdi_procesados ADD COLUMN huella TEXT")
    con.script(INDICES)
