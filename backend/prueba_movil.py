"""
Prueba de STOCK como app instalable en el celular (PWA).

Uso:  python prueba_movil.py [url_base]     (por defecto https://stock-tienda.onrender.com)
Revisa: manifiesto e íconos, service worker, que Chrome/Edge la consideren instalable, que abra sin internet,
el aviso de sin señal, la ventana de instalar en iPhone y que en iPhone no haga zoom al escribir.
"""
import sys

import httpx
from playwright.sync_api import sync_playwright

from ayuda_pruebas import PIN, entrar

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://stock-tienda.onrender.com").rstrip("/")
ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
resultados = []


def escribir_pin(page):
    """Escribe el PIN en la pantalla del PIN (teclado físico) y espera a que se cierre."""
    page.wait_for_selector("#pantallaPin:not(.hidden)", timeout=30000)
    page.keyboard.type(PIN)
    page.keyboard.press("Enter")
    page.wait_for_selector("#pantallaPin.hidden", state="attached", timeout=30000)


def prueba(nombre, f):
    try:
        resultados.append((True, nombre, f() or "ok"))
    except Exception as e:  # noqa: BLE001
        resultados.append((False, nombre, f"{type(e).__name__}: {str(e)[:250]}"))
    ok, _, det = resultados[-1]
    print(f"{'✅' if ok else '❌'} {nombre}: {det}", flush=True)


def manifiesto():
    r = httpx.get(BASE + "/manifest.webmanifest", timeout=90)
    assert r.status_code == 200 and "manifest+json" in r.headers["content-type"], (r.status_code, r.headers.get("content-type"))
    m = r.json()
    assert m["display"] == "standalone" and m["start_url"] == "/app" and m["short_name"] == "STOCK"
    tamaños = set()
    for icono in m["icons"]:
        ri = httpx.get(BASE + icono["src"], timeout=60)
        assert ri.status_code == 200 and ri.headers["content-type"] == "image/png", icono["src"]
        tamaños.add(icono["sizes"])
    assert {"192x192", "512x512"} <= tamaños and any(i.get("purpose") == "maskable" for i in m["icons"])
    ra = httpx.get(BASE + "/static/iconos/apple-touch-icon.png", timeout=60)
    assert ra.status_code == 200
    return f"{len(m['icons'])} íconos, {len(m['shortcuts'])} accesos directos, ícono de iPhone"


def service_worker_http():
    r = httpx.get(BASE + "/sw.js", timeout=60)
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert r.headers.get("service-worker-allowed") == "/" and r.headers.get("cache-control") == "no-cache"
    assert "cdn.tailwindcss.com" in r.headers["content-security-policy"]
    assert "connect-src 'self';" in httpx.get(BASE + "/app", timeout=60).headers["content-security-policy"], \
        "la página no debe heredar la CSP ampliada del service worker"
    return "en la raíz, sin caché y con su propia CSP"


entrar(httpx.Client(base_url=BASE, timeout=90))  # crea el PIN de prueba si la tienda no tiene
VERSION_LEGAL = httpx.get(BASE + "/api/acceso/estado", timeout=90).json()["legal_version"]
# Este "celular" ya aceptó el aviso y los términos (eso se prueba en prueba_legal.py)
YA_ACEPTO = ("localStorage.setItem('stock_bienvenida','1');"
             f"localStorage.setItem('stock_legal_aceptado', JSON.stringify({{version: '{VERSION_LEGAL}', fecha: '2026-11-20'}}))")

with sync_playwright() as pw:
    nav = pw.chromium.launch(channel="msedge", headless=True)

    def android():
        ctx = nav.new_context(viewport={"width": 412, "height": 915}, device_scale_factor=2.6, is_mobile=True,
                              has_touch=True, user_agent=ANDROID, locale="es-MX")
        ctx.add_init_script(YA_ACEPTO)
        page = ctx.new_page()
        errores = []
        page.on("pageerror", lambda e: errores.append(str(e)))
        page.goto(BASE + "/app", wait_until="networkidle", timeout=120000)
        escribir_pin(page)
        page.evaluate("navigator.serviceWorker.ready.then(() => true)")
        page.reload(wait_until="networkidle")
        assert page.evaluate("!!navigator.serviceWorker.controller"), "el service worker no tomó el control"
        cdp = ctx.new_cdp_session(page)
        # "in-incognito" solo indica que la prueba corre en ventana privada; cualquier otro motivo es una falla real
        errores_inst = [e for e in cdp.send("Page.getInstallabilityErrors")["installabilityErrors"]
                        if e["errorId"] != "in-incognito"]
        assert not errores_inst, f"no es instalable: {errores_inst}"
        cdp.detach()
        # Sin internet: la app abre desde la copia y avisa
        ctx.set_offline(True)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#avisoSinRed", state="visible", timeout=15000)  # falla si no sale el aviso
        assert "STOCK" in page.title(), page.title()
        fondo = page.evaluate("getComputedStyle(document.querySelector('header')).backdropFilter || getComputedStyle(document.querySelector('header')).webkitBackdropFilter")
        assert fondo and fondo != "none", "sin internet abrió sin estilos (Tailwind no quedó en caché)"
        ctx.set_offline(False)
        page.wait_for_selector("#avisoSinRed", state="hidden", timeout=15000)  # el aviso se quita al volver la señal
        assert not errores, errores[:2]
        ctx.close()
        return "instalable, service worker activo, abre sin internet con estilos y aviso, y se recupera"

    def iphone():
        ctx = nav.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True,
                              has_touch=True, user_agent=IPHONE, locale="es-MX")
        ctx.add_init_script(YA_ACEPTO)
        page = ctx.new_page()
        page.goto(BASE + "/app", wait_until="networkidle", timeout=120000)
        escribir_pin(page)
        tam = page.evaluate("getComputedStyle(document.getElementById('inputTexto')).fontSize")
        assert tam == "16px", f"el campo de texto mide {tam}: iPhone haría zoom al escribir"
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        page.click("#btnMenu")
        page.click("[data-menu='instalar']")
        page.wait_for_selector("#confirmar:not(.hidden)")
        texto = page.inner_text("#confTexto")
        assert "Agregar a pantalla de inicio" in texto and page.locator("#confNo").is_hidden(), texto[:80]
        page.click("#confSi")
        ctx.close()
        return "sin zoom al escribir (16 px), sin desborde e instrucciones de Safari para instalar"

    prueba("M1. Manifiesto e íconos", manifiesto)
    prueba("M2. Service worker servido bien", service_worker_http)
    prueba("M3. Android: instalable y funciona sin internet", android)
    prueba("M4. iPhone: instalar desde Safari y teclado sin zoom", iphone)
    nav.close()

fallas = sum(not ok for ok, *_ in resultados)
print(f"\n{len(resultados) - fallas}/{len(resultados)} pruebas de app móvil pasaron")
sys.exit(1 if fallas else 0)
