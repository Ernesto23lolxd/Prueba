# =====================================================================================================
# 🔑 acceso.py — el PIN de la tienda y la sesión
# El PIN nunca se guarda (solo su huella scrypt), la sesión es una cookie firmada y hay freno anti-adivinanzas.
# =====================================================================================================
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

# 👉 Nombre de la cookie de sesión
COOKIE = "stock_sesion"
# Versión vigente del Aviso de Privacidad y los Términos (app/privacidad.html y app/terminos.html).
# Si cambian, se sube este valor y todas las tiendas deben aceptarlos otra vez al entrar.
# 👉 Versión del aviso de privacidad y términos. Si los cambian, súbanle aquí y todos tendrán que aceptarlos otra vez
LEGAL_VERSION = "1.1-2026-11-20"
# 👉 Cuánto dura la sesión: 30 días
DURACION = 30 * 24 * 3600
VENTANA_IP, MAX_IP = 15 * 60, 5
VENTANA_GLOBAL, MAX_GLOBAL = 3600, 30
# 👉 PINs demasiado fáciles que no dejamos usar
TRIVIALES = {"0000", "1111", "1234", "4321", "00000", "12345", "000000", "111111", "123456", "654321",
             "2222", "3333", "4444", "5555", "6666", "7777", "8888", "9999", "123123", "112233"}


# 👉 Revisa que el PIN tenga 4 a 6 números y no sea obvio (1234, 0000…)
def pin_valido(pin: str) -> str | None:
    """Regresa un mensaje de error o None si el PIN sirve."""
    if not re.fullmatch(r"\d{4,6}", pin or ""):
        return "El PIN debe tener de 4 a 6 números."
    if pin in TRIVIALES or len(set(pin)) == 1:
        return "Ese PIN es muy fácil de adivinar. Usa otro."
    return None


# 👉 Bytes → texto base64 (para guardar la sal y la huella)
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


# 👉 Texto base64 → bytes
def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# 👉 Saca la huella del PIN con scrypt + sal al azar (lento a propósito para que adivinar cueste)
def huella_pin(pin: str, sal: bytes | None = None) -> str:
    sal = sal or os.urandom(16)
    h = hashlib.scrypt(pin.encode(), salt=sal, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${_b64(sal)}${_b64(h)}"


# 👉 Compara el PIN con la huella guardada (comparación en tiempo constante)
def pin_correcto(pin: str, guardado: str | None) -> bool:
    try:
        _, sal, h = (guardado or "").split("$")
        return hmac.compare_digest(huella_pin(pin, _unb64(sal)).split("$")[2], h)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- Ajustes en la base (tabla "ajustes")
# 👉 Lee un ajuste de la tabla 'ajustes' (PIN, versión legal, secreto…)
def leer(con, clave: str) -> str | None:
    fila = con.execute("SELECT valor FROM ajustes WHERE clave=?", (clave,)).fetchone()
    return fila["valor"] if fila else None


# 👉 Guarda o borra un ajuste (upsert: si existe lo actualiza)
def guardar(con, clave: str, valor: str | None):
    if valor is None:
        con.execute("DELETE FROM ajustes WHERE clave=?", (clave,))
    else:
        con.execute("INSERT INTO ajustes (clave, valor) VALUES (?, ?) "
                    "ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor", (clave, valor))


# 👉 La llave secreta para firmar sesiones (se crea sola la primera vez)
def secreto(con) -> str:
    s = leer(con, "secreto_sesion")
    if not s:
        s = secrets.token_hex(32)
        guardar(con, "secreto_sesion", s)
        con.commit()
    return s


# ---------------------------------------------------------------- Sesiones firmadas
# 👉 Arma el token de sesión: vencimiento + versión del PIN + firma HMAC
def crear_token(con) -> str:
    version = leer(con, "pin_version") or "1"
    carga = f"{int(time.time()) + DURACION}.{version}"
    firma = hmac.new(secreto(con).encode(), carga.encode(), hashlib.sha256).hexdigest()
    return f"{carga}.{firma}"


# 👉 ¿La tienda ya aceptó la versión vigente del aviso y los términos?
def legal_aceptado(con) -> bool:
    return leer(con, "legal_version") == LEGAL_VERSION


# 👉 Guarda la constancia: qué versión aceptó y cuándo (UTC)
def guardar_aceptacion(con):
    """Constancia del consentimiento: qué versión se aceptó y cuándo (UTC)."""
    from datetime import datetime, timezone
    guardar(con, "legal_version", LEGAL_VERSION)
    guardar(con, "legal_aceptado_en", datetime.now(timezone.utc).isoformat(timespec="seconds"))


# 👉 Revisa firma, vencimiento y versión del PIN de la sesión (si cambiaron el PIN, las viejas ya no sirven)
def token_valido(con, token: str | None) -> bool:
    try:
        vence, version, firma = (token or "").split(".")
        carga = f"{vence}.{version}"
        esperada = hmac.new(secreto(con).encode(), carga.encode(), hashlib.sha256).hexdigest()
        return (hmac.compare_digest(firma, esperada) and int(vence) > time.time()
                and version == (leer(con, "pin_version") or "1") and leer(con, "pin_huella") is not None)
    except (ValueError, TypeError):
        return False


# 👉 Pega la cookie: HttpOnly (JS no la lee), SameSite=Strict (otro sitio no la usa), Secure en HTTPS
def poner_cookie(respuesta, token: str, https: bool):
    respuesta.set_cookie(COOKIE, token, max_age=DURACION, httponly=True, samesite="strict", secure=https, path="/")


# 👉 Borra la cookie (bloquear)
def quitar_cookie(respuesta, https: bool):
    respuesta.delete_cookie(COOKIE, httponly=True, samesite="strict", secure=https, path="/")


# ---------------------------------------------------------------- Freno contra adivinar el PIN
# 👉 El freno anti-adivinanzas: cuenta fallos por IP y en total
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

    # 👉 ¿Ya se pasó de intentos esta IP (o todos juntos)?
    def bloqueado(self, ip: str) -> bool:
        self._limpiar(ip)
        return len(self.por_ip[ip]) >= MAX_IP or len(self.todos) >= MAX_GLOBAL

    # 👉 Cuántos intentos le quedan (para decírselo al usuario)
    def restantes(self, ip: str) -> int:
        self._limpiar(ip)
        return max(0, MAX_IP - len(self.por_ip[ip]))

    # 👉 Anota un intento fallido
    def fallo(self, ip: str):
        ahora = time.monotonic()
        self.por_ip[ip].append(ahora)
        self.todos.append(ahora)

    # 👉 Si atinó, le borramos sus fallos
    def exito(self, ip: str):
        self.por_ip.pop(ip, None)


intentos = Intentos()
