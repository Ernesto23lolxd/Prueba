"""
PIN de acceso por tienda.

- El PIN (4 a 6 números) NUNCA se guarda: solo su huella con scrypt + sal aleatoria.
- Al entrar, el servidor da una cookie de sesión HttpOnly (JavaScript no la puede leer), SameSite=Strict
  (otro sitio no la puede usar) y Secure en HTTPS, firmada con HMAC-SHA256 y válida 30 días.
- Cambiar el PIN invalida todas las sesiones abiertas (versión del PIN dentro de la firma).
- Contra adivinanzas: 5 intentos fallidos por IP cada 15 minutos y 30 en total por hora → bloqueo temporal.
- Olvido del PIN: el administrador pone RESETEAR_PIN=1 en el servidor, reinicia y se crea uno nuevo.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from collections import defaultdict, deque

COOKIE = "stock_sesion"
DURACION = 30 * 24 * 3600
VENTANA_IP, MAX_IP = 15 * 60, 5
VENTANA_GLOBAL, MAX_GLOBAL = 3600, 30
TRIVIALES = {"0000", "1111", "1234", "4321", "00000", "12345", "000000", "111111", "123456", "654321",
             "2222", "3333", "4444", "5555", "6666", "7777", "8888", "9999", "123123", "112233"}


def pin_valido(pin: str) -> str | None:
    """Regresa un mensaje de error o None si el PIN sirve."""
    if not re.fullmatch(r"\d{4,6}", pin or ""):
        return "El PIN debe tener de 4 a 6 números."
    if pin in TRIVIALES or len(set(pin)) == 1:
        return "Ese PIN es muy fácil de adivinar. Usa otro."
    return None


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def huella_pin(pin: str, sal: bytes | None = None) -> str:
    sal = sal or os.urandom(16)
    h = hashlib.scrypt(pin.encode(), salt=sal, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${_b64(sal)}${_b64(h)}"


def pin_correcto(pin: str, guardado: str | None) -> bool:
    try:
        _, sal, h = (guardado or "").split("$")
        return hmac.compare_digest(huella_pin(pin, _unb64(sal)).split("$")[2], h)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- Ajustes en la base (tabla "ajustes")
def leer(con, clave: str) -> str | None:
    fila = con.execute("SELECT valor FROM ajustes WHERE clave=?", (clave,)).fetchone()
    return fila["valor"] if fila else None


def guardar(con, clave: str, valor: str | None):
    if valor is None:
        con.execute("DELETE FROM ajustes WHERE clave=?", (clave,))
    else:
        con.execute("INSERT INTO ajustes (clave, valor) VALUES (?, ?) "
                    "ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor", (clave, valor))


def secreto(con) -> str:
    s = leer(con, "secreto_sesion")
    if not s:
        s = secrets.token_hex(32)
        guardar(con, "secreto_sesion", s)
        con.commit()
    return s


# ---------------------------------------------------------------- Sesiones firmadas
def crear_token(con) -> str:
    version = leer(con, "pin_version") or "1"
    carga = f"{int(time.time()) + DURACION}.{version}"
    firma = hmac.new(secreto(con).encode(), carga.encode(), hashlib.sha256).hexdigest()
    return f"{carga}.{firma}"


def token_valido(con, token: str | None) -> bool:
    try:
        vence, version, firma = (token or "").split(".")
        carga = f"{vence}.{version}"
        esperada = hmac.new(secreto(con).encode(), carga.encode(), hashlib.sha256).hexdigest()
        return (hmac.compare_digest(firma, esperada) and int(vence) > time.time()
                and version == (leer(con, "pin_version") or "1") and leer(con, "pin_huella") is not None)
    except (ValueError, TypeError):
        return False


def poner_cookie(respuesta, token: str, https: bool):
    respuesta.set_cookie(COOKIE, token, max_age=DURACION, httponly=True, samesite="strict", secure=https, path="/")


def quitar_cookie(respuesta, https: bool):
    respuesta.delete_cookie(COOKIE, httponly=True, samesite="strict", secure=https, path="/")


# ---------------------------------------------------------------- Freno contra adivinar el PIN
class Intentos:
    def __init__(self):
        self.por_ip: dict[str, deque] = defaultdict(deque)
        self.todos: deque = deque()

    def _limpiar(self, ip: str):
        ahora = time.monotonic()
        while self.por_ip[ip] and ahora - self.por_ip[ip][0] > VENTANA_IP:
            self.por_ip[ip].popleft()
        while self.todos and ahora - self.todos[0] > VENTANA_GLOBAL:
            self.todos.popleft()

    def bloqueado(self, ip: str) -> bool:
        self._limpiar(ip)
        return len(self.por_ip[ip]) >= MAX_IP or len(self.todos) >= MAX_GLOBAL

    def restantes(self, ip: str) -> int:
        self._limpiar(ip)
        return max(0, MAX_IP - len(self.por_ip[ip]))

    def fallo(self, ip: str):
        ahora = time.monotonic()
        self.por_ip[ip].append(ahora)
        self.todos.append(ahora)

    def exito(self, ip: str):
        self.por_ip.pop(ip, None)


intentos = Intentos()
