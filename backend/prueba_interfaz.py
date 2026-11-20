"""
Pruebas de interfaz en muchos dispositivos (Playwright con el Edge instalado; simula pantalla, toque y user agent).

Uso:  python prueba_interfaz.py [url_base] [carpeta_capturas]
Revisa en cada dispositivo: que nada se salga de la pantalla, la bienvenida, los 17 pasos del tutorial
(tarjeta y foco dentro de la pantalla, sin tapar lo resaltado), las 6 secciones, el menú ⋯, la confirmación,
la tienda de ejemplo, botones − / +, que un nombre con HTML no ejecute código y que no haya errores de JavaScript.
"""
import sys
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

from ayuda_pruebas import PIN, entrar

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
CAPTURAS = Path(sys.argv[2]) if len(sys.argv) > 2 else None
if CAPTURAS:
    CAPTURAS.mkdir(parents=True, exist_ok=True)

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
IPAD = "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
DISPOSITIVOS = [
    # nombre, ancho, alto, escala, móvil/táctil, user agent
    ("Android chico 320×640", 320, 640, 2, True, ANDROID),
    ("Galaxy A 360×780", 360, 780, 3, True, ANDROID),
    ("iPhone SE 375×667", 375, 667, 2, True, IPHONE),
    ("iPhone 15 393×852", 393, 852, 3, True, IPHONE),
    ("Pixel 8 412×915", 412, 915, 2.6, True, ANDROID),
    ("iPhone 15 Pro Max 430×932", 430, 932, 3, True, IPHONE),
    ("Celular horizontal 844×390", 844, 390, 3, True, IPHONE),
    ("iPad mini 768×1024", 768, 1024, 2, True, IPAD),
    ("iPad Pro horizontal 1366×1024", 1366, 1024, 2, True, IPAD),
    ("Laptop 1280×720", 1280, 720, 1, False, None),
    ("Escritorio 1920×1080", 1920, 1080, 1, False, None),
    ("Monitor 2560×1440", 2560, 1440, 1, False, None),
]

api = httpx.Client(base_url=BASE, timeout=60)
entrar(api)
resultados = []


def escribir_pin(page):
    """Escribe el PIN en la pantalla del PIN (teclado físico) y espera a que se cierre."""
    page.wait_for_selector("#pantallaPin:not(.hidden)", timeout=30000)
    page.keyboard.type(PIN)
    page.keyboard.press("Enter")
    page.wait_for_selector("#pantallaPin.hidden", state="attached", timeout=30000)


def reporte(ok, nombre, detalle):
    resultados.append((ok, nombre, detalle))
    print(f"{'✅' if ok else '❌'} {nombre}: {detalle}", flush=True)


DESBORDE_JS = """() => {
  const W = document.documentElement.clientWidth;
  const fuera = [];
  document.querySelectorAll('body *').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || el.closest('.hidden')) return;
    if (el.closest('#toastContainer')) return;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && (r.right > W + 1 || r.left < -1)) fuera.push((el.id || el.tagName) + ' ' + Math.round(r.left) + '..' + Math.round(r.right));
  });
  return {W, sw: document.documentElement.scrollWidth, fuera: fuera.slice(0, 6)};
}"""


def sin_desborde(page, donde):
    d = page.evaluate(DESBORDE_JS)
    assert d["sw"] <= d["W"] + 1, f"{donde}: la página mide {d['sw']}px en una pantalla de {d['W']}px ({d['fuera']})"
    return d


def dentro(r, ancho, alto, margen=2):
    return r["x"] >= -margen and r["y"] >= -margen and r["x"] + r["width"] <= ancho + margen and r["y"] + r["height"] <= alto + margen


def probar_dispositivo(pw_navegador, nombre, ancho, alto, escala, movil, ua):
    errores = []
    contexto = pw_navegador.new_context(viewport={"width": ancho, "height": alto}, device_scale_factor=escala,
                                        is_mobile=movil and ancho < 1000, has_touch=movil, user_agent=ua,
                                        locale="es-MX", reduced_motion="reduce", bypass_csp=True)  # solo para que la prueba pueda esperar condiciones
    page = contexto.new_page()
    page.on("pageerror", lambda e: errores.append(f"pageerror: {e}"))
    page.on("console", lambda m: errores.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("response", lambda r: errores.append(f"HTTP {r.status} {r.url}") if r.status >= 400 and "/api/" not in r.url else None)
    page.on("dialog", lambda d: (errores.append(f"diálogo inesperado: {d.message}"), d.dismiss()))
    corto = nombre.split(" ")[0] + "_" + str(ancho)
    try:
        api.post("/api/reset", json={"modo": "vacio", "pin": PIN})
        # 1. Portada
        page.goto(BASE + "/", wait_until="networkidle")
        sin_desborde(page, "portada")
        if CAPTURAS:
            page.screenshot(path=str(CAPTURAS / f"{corto}_portada.png"))

        # 2. Bienvenida (primera vez)
        page.goto(BASE + "/app", wait_until="networkidle")
        page.wait_for_selector("#pantallaLegal:not(.hidden)", timeout=8000)  # lo primero: aceptar aviso y términos
        assert page.locator("#bienvenida").is_hidden(), "la bienvenida salió antes del aviso legal"
        sin_desborde(page, "aviso legal")
        page.check("#legalCheck")
        page.click("#legalAceptar")
        page.wait_for_selector("#bienvenida:not(.hidden)", timeout=8000)
        sin_desborde(page, "bienvenida")
        page.fill("#bvNombre", "Abarrotes Lupita")
        boton = page.locator("#bvTutorial")
        boton.scroll_into_view_if_needed()
        assert boton.is_visible(), "no se ve el botón del tutorial"
        if CAPTURAS:
            page.screenshot(path=str(CAPTURAS / f"{corto}_bienvenida.png"))
        boton.click()
        escribir_pin(page)  # después de la bienvenida se pide el PIN de la tienda

        # 3. Tutorial: los 17 pasos
        page.wait_for_selector("#tour:not(.hidden)")
        total = page.evaluate("PASOS.length")
        problemas = []
        for paso in range(total):
            page.wait_for_timeout(1000)  # deja terminar el desplazamiento suave
            tarjeta = page.locator("#tourTarjeta").bounding_box()
            if not dentro(tarjeta, ancho, alto):
                problemas.append(f"paso {paso + 1}: la tarjeta se sale de la pantalla {tarjeta}")
            info = page.evaluate("""() => {
                const p = PASOS[tourPaso];
                if (!p.el) return null;
                const el = document.querySelector(p.el);
                const r = el.getBoundingClientRect();
                const f = document.getElementById('tourFoco').getBoundingClientRect();
                return {r: {x: r.x, y: r.y, w: r.width, h: r.height}, f: {x: f.x, y: f.y, w: f.width, h: f.height},
                        visible: r.width > 0 && r.height > 0};
            }""")
            if info:
                if not info["visible"]:
                    problemas.append(f"paso {paso + 1}: el elemento resaltado no se ve")
                f = info["f"]
                if f["h"] < 20 or f["w"] < 20:
                    problemas.append(f"paso {paso + 1}: casi no se ve lo resaltado ({round(f['w'])}×{round(f['h'])})")
                cy = f["y"] + f["h"] / 2
                cx = f["x"] + f["w"] / 2
                # el centro de lo resaltado debe verse (en pantalla y no tapado por la tarjeta)
                if not (0 <= cy <= alto and 0 <= cx <= ancho):
                    problemas.append(f"paso {paso + 1}: lo resaltado quedó fuera de la pantalla")
                elif (tarjeta["x"] <= cx <= tarjeta["x"] + tarjeta["width"]
                      and tarjeta["y"] <= cy <= tarjeta["y"] + tarjeta["height"]
                      and f["h"] < alto * 0.6):
                    problemas.append(f"paso {paso + 1}: la tarjeta tapa lo que está resaltado")
            if CAPTURAS and paso in (2, 6, 9, 16):
                page.screenshot(path=str(CAPTURAS / f"{corto}_tutorial_{paso + 1}.png"))
            page.click("#tourSig")
        page.wait_for_selector("#tour.hidden", state="attached")
        assert not problemas, "; ".join(problemas[:4])
        assert "Abarrotes Lupita" in page.inner_text("#subtituloTienda"), "no se guardó el nombre de la tienda"

        # 4. Inicio en ceros
        assert page.locator("#tiendaVacia").is_visible(), "no se ve la guía de tienda en ceros"
        sin_desborde(page, "inicio en ceros")

        # 5. Menú ⋯ y confirmación → tienda de ejemplo
        page.click("#btnMenu")
        menu = page.locator("#menuOpciones").bounding_box()
        assert dentro(menu, ancho, alto), f"el menú se sale de la pantalla {menu}"
        page.click("[data-menu='demo']")
        page.wait_for_selector("#confirmar:not(.hidden)")
        assert dentro(page.locator("#confirmar > div").bounding_box(), ancho, alto), "la confirmación se sale"
        page.click("#confSi")
        escribir_pin(page)  # cargar la tienda de ejemplo pide el PIN otra vez
        page.wait_for_function("document.querySelectorAll('#inventario [data-campo], #inventario button').length > 0 || (tablero.prediccion||[]).length > 0", timeout=15000)
        assert not page.locator("#tiendaVacia").is_visible(), "sigue la guía de ceros con productos"

        # 6. Las 6 secciones, sin desbordes
        for vista in ("inicio", "alertas", "surtir", "parado", "inventario", "mes"):
            page.locator(f"[data-vista-btn='{vista}']").click()
            page.wait_for_timeout(250)
            caja = page.locator(f"[data-vista-btn='{vista}']").bounding_box()
            assert caja["height"] >= 32 and caja["width"] >= 40, f"botón {vista} muy chico para el dedo {caja}"
            sin_desborde(page, f"sección {vista}")
            if CAPTURAS:
                page.screenshot(path=str(CAPTURAS / f"{corto}_{vista}.png"), full_page=False)

        # 7. Botón + del inventario (sin IA)
        page.locator("[data-vista-btn='inventario']").click()
        antes = api.get("/api/inventario").json()
        page.evaluate("window.scrollTo(0, 0)")
        mas = page.locator("#inventario [data-delta='1'], #inventario [data-delta='0.5']").first
        mas.scroll_into_view_if_needed()
        page.evaluate("window.scrollBy(0, -120)")  # que no quede debajo del encabezado fijo
        mas.click()
        page.wait_for_timeout(1200)
        despues = api.get("/api/inventario").json()
        assert sum(p["cantidad"] for p in despues) == sum(p["cantidad"] for p in antes) + 1, "el botón + no sumó 1"

        # 8. Un nombre con HTML no ejecuta código
        pid = despues[0]["id"]
        api.patch(f"/api/productos/{pid}", json={"nombre": '<img src=x onerror="window.__xss=1">Prueba'})
        page.evaluate("cargarTablero()")
        page.wait_for_timeout(1200)
        assert not page.evaluate("window.__xss === 1"), "¡se ejecutó código desde el nombre de un producto!"
        page.locator("[data-vista-btn='inicio']").click()
        page.click("#btnMenu")
        page.click("[data-menu='cero']")
        page.click("#confSi")
        escribir_pin(page)  # empezar de cero pide el PIN otra vez
        page.wait_for_selector("#tiendaVacia:not(.hidden)", timeout=10000)

        # 9. El botón ? repite el tutorial
        page.click("#btnTutorial")
        page.wait_for_selector("#tour:not(.hidden)")
        page.keyboard.press("Escape") if not movil else page.click("#tourCerrar")
        page.wait_for_selector("#tour.hidden", state="attached")

        errores_js = [e for e in errores if "favicon" not in e]
        assert not errores_js, f"errores de JavaScript: {errores_js[:3]}"
        reporte(True, nombre, f"bienvenida, {total} pasos del tutorial, 6 secciones, menú, ejemplo, + y XSS ok")
    except Exception as e:  # noqa: BLE001
        reporte(False, nombre, f"{type(e).__name__}: {str(e)[:300]}" + (f" | JS: {errores[:2]}" if errores else ""))
        if CAPTURAS:
            page.screenshot(path=str(CAPTURAS / f"{corto}_FALLA.png"))
    finally:
        contexto.close()


with sync_playwright() as pw:
    navegador = pw.chromium.launch(channel="msedge", headless=True)
    for disp in [d for d in DISPOSITIVOS if (len(sys.argv) < 4 or sys.argv[3] in d[0])]:
        probar_dispositivo(navegador, *disp)
    navegador.close()

api.post("/api/reset", json={"modo": "vacio", "pin": PIN})
fallas = sum(not ok for ok, *_ in resultados)
print(f"\n{len(resultados) - fallas}/{len(resultados)} dispositivos sin problemas")
sys.exit(1 if fallas else 0)
