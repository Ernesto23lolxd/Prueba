"""
Prueba del registro de la tienda con aceptación del Aviso de Privacidad y los Términos (Playwright).

Uso:  python prueba_legal.py [url_base]
Simula una tienda NUEVA interceptando /api/acceso/* en el navegador (no toca la tienda real del servidor) y revisa:
la pantalla "Antes de empezar", que sin la casilla no se pueda seguir, "No acepto", el lector de ambos documentos,
que el registro mande la versión aceptada y, con documentos nuevos, que una tienda existente tenga que aceptarlos.
"""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://stock-tienda.onrender.com").rstrip("/")
VERSION = "9.9-prueba"
resultados = []


def prueba(nombre, f):
    try:
        resultados.append((True, nombre, f() or "ok"))
    except Exception as e:  # noqa: BLE001
        resultados.append((False, nombre, f"{type(e).__name__}: {str(e)[:260]}"))
    ok, _, det = resultados[-1]
    print(f"{'✅' if ok else '❌'} {nombre}: {det}", flush=True)


def simular(page, configurado: bool, enviados: list):
    def responder(route, request):
        ruta = request.url.split("/api/acceso/")[1].split("?")[0]
        if ruta == "estado":
            cuerpo = {"configurado": configurado, "sesion": False, "legal_version": VERSION, "legal_aceptado": False}
        else:
            enviados.append((ruta, json.loads(request.post_data or "{}")))
            cuerpo = {"ok": True}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))
    page.route("**/api/acceso/**", responder)
    # El resto de la API sin sesión: respuestas vacías para que la app no insista en pedir el PIN
    page.route("**/api/tablero*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"prediccion": [], "resumen": {"valor_inventario": 0, "efectivo_apartar": 0, "capital_congelado": 0,
                                       "productos_criticos": 0, "productos_lentos": 0, "urgentes_lista": 0,
                                       "salud_porcentaje": 0, "no_pedir": []},
         "lista": {"items": [], "por_proveedor": [], "total_estimado": 0}, "movimientos": []})))
    page.route("**/api/resumen-mes", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"mes": "noviembre 2026", "vendido": {"monto": 0, "movimientos": 0}, "surtido": {"monto": 0, "facturas": 0},
         "dinero_parado": {"monto": 0}, "ultimas_facturas": []})))


with sync_playwright() as pw:
    nav = pw.chromium.launch(channel="msedge", headless=True)

    def registro_nuevo():
        ctx = nav.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, bypass_csp=True)
        ctx.add_init_script("localStorage.setItem('stock_bienvenida','1')")
        page = ctx.new_page()
        errores, enviados = [], []
        page.on("pageerror", lambda e: errores.append(str(e)))
        simular(page, configurado=False, enviados=enviados)
        page.goto(BASE + "/app", wait_until="networkidle", timeout=120000)
        page.wait_for_selector("#pantallaLegal:not(.hidden)", timeout=20000)
        assert page.locator("#pantallaPin").is_hidden(), "el PIN no debe salir antes de aceptar"
        assert page.locator("#legalAceptar").is_disabled(), "se puede aceptar sin marcar la casilla"
        page.click("#legalNo")
        assert page.locator("#legalAviso").is_visible() and page.locator("#pantallaLegal").is_visible(), "No acepto dejó pasar"
        for doc, frase in (("privacidad", "Aviso de Privacidad Integral"), ("terminos", "Términos y Condiciones de Uso")):
            page.click(f"[data-leer='{doc}']")
            page.wait_for_selector("#lectorLegal:not(.hidden)")
            page.wait_for_function(f"document.getElementById('lectorTexto').innerText.includes('{frase}')", timeout=20000)
            caja = page.locator("#lectorLegal > div").bounding_box()
            assert caja["width"] <= 390 + 1, f"el lector se sale de la pantalla: {caja}"
            page.click("#lectorCerrar")
        page.check("#legalCheck")
        assert page.locator("#legalAceptar").is_enabled()
        page.click("#legalAceptar")
        page.wait_for_selector("#pantallaPin:not(.hidden)")
        assert "Crea tu PIN" in page.inner_text("#pinTitulo")
        for _ in range(2):
            page.keyboard.type("482915")
            page.keyboard.press("Enter")
            page.wait_for_timeout(300)
        page.wait_for_selector("#pantallaPin.hidden", state="attached", timeout=15000)
        crear = [b for r, b in enviados if r == "crear"]
        assert crear and crear[0] == {"pin": "482915", "acepto_legal": VERSION}, f"el registro no mandó la aceptación: {enviados}"
        assert not errores, errores[:2]
        ctx.close()
        return "casilla obligatoria, 'No acepto' bloquea, lector de ambos documentos y registro con la versión aceptada"

    def documentos_nuevos():
        ctx = nav.new_context(viewport={"width": 1280, "height": 800}, bypass_csp=True)
        ctx.add_init_script("localStorage.setItem('stock_bienvenida','1')")
        page = ctx.new_page()
        enviados = []
        simular(page, configurado=True, enviados=enviados)
        page.goto(BASE + "/app", wait_until="networkidle", timeout=120000)
        page.wait_for_selector("#pantallaLegal:not(.hidden)", timeout=20000)
        assert "Actualizamos" in page.inner_text("#legalTitulo")
        page.check("#legalCheck")
        page.click("#legalAceptar")
        page.wait_for_selector("#pantallaPin:not(.hidden)")
        assert "Ingresa tu PIN" in page.inner_text("#pinTitulo")
        page.keyboard.type("482915")
        page.keyboard.press("Enter")
        page.wait_for_selector("#pantallaPin.hidden", state="attached", timeout=15000)
        entrar = [b for r, b in enviados if r == "entrar"]
        assert entrar and entrar[0].get("acepto_legal") == VERSION, enviados
        ctx.close()
        return "una tienda existente debe aceptar la versión nueva antes de entrar"

    def menu_legal():
        ctx = nav.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, bypass_csp=True)
        ctx.add_init_script("localStorage.setItem('stock_bienvenida','1')")
        page = ctx.new_page()
        simular(page, configurado=True, enviados=[])
        page.goto(BASE + "/privacidad", wait_until="networkidle", timeout=120000)
        assert page.evaluate("document.documentElement.scrollWidth") <= 391, "el aviso se sale de la pantalla"
        page.goto(BASE + "/terminos", wait_until="networkidle", timeout=120000)
        assert page.evaluate("document.documentElement.scrollWidth") <= 391, "los términos se salen de la pantalla"
        ctx.close()
        return "/privacidad y /terminos se leen bien en celular"

    prueba("L1. Registro nuevo: leer y aceptar es obligatorio antes de crear el PIN", registro_nuevo)
    prueba("L2. Documentos nuevos: la tienda existente los acepta antes de entrar", documentos_nuevos)
    prueba("L3. Páginas públicas del aviso y los términos en celular", menu_legal)
    nav.close()

fallas = sum(not ok for ok, *_ in resultados)
print(f"\n{len(resultados) - fallas}/{len(resultados)} pruebas legales pasaron")
sys.exit(1 if fallas else 0)
