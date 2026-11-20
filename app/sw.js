/* STOCK · service worker
 * - La app (HTML) se pide primero a internet y se guarda copia: si no hay señal, abre la última copia.
 * - Archivos fijos (íconos, Tailwind, fuentes): se sirven de la copia y se actualizan en segundo plano.
 * - La API (/api/...) NUNCA se guarda: el inventario siempre es el real del servidor.
 */
const VERSION = "stock-v1";
const BASICOS = ["/app", "/", "/manifest.webmanifest", "/static/iconos/icono-192.png", "/static/iconos/icono-512.png"];
const EXTERNOS_PERMITIDOS = ["https://cdn.tailwindcss.com", "https://fonts.googleapis.com", "https://fonts.gstatic.com"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(BASICOS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((nombres) => Promise.all(nombres.filter((n) => n !== VERSION).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

async function primeroInternet(peticion) {
  const cache = await caches.open(VERSION);
  try {
    const resp = await fetch(peticion);
    if (resp.ok) cache.put(peticion, resp.clone());
    return resp;
  } catch (_) {
    const url = new URL(peticion.url);
    return (await cache.match(peticion, { ignoreSearch: true }))
      || (await cache.match(url.pathname === "/" ? "/" : "/app"))
      || new Response("<h1>Sin internet</h1><p>Conéctate para usar STOCK.</p>", { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } });
  }
}

async function copiaYActualiza(peticion) {
  const cache = await caches.open(VERSION);
  const guardada = await cache.match(peticion);
  const nueva = fetch(peticion)
    .then((resp) => { if (resp.ok || resp.type === "opaque") cache.put(peticion, resp.clone()); return resp; })
    .catch(() => guardada);
  return guardada || nueva;
}

self.addEventListener("fetch", (e) => {
  const peticion = e.request;
  if (peticion.method !== "GET") return;
  const url = new URL(peticion.url);
  if (url.origin === self.location.origin) {
    if (url.pathname.startsWith("/api/")) return;              // datos: siempre del servidor
    if (peticion.mode === "navigate") return e.respondWith(primeroInternet(peticion));
    if (url.pathname.startsWith("/static/") || url.pathname === "/manifest.webmanifest") {
      return e.respondWith(copiaYActualiza(peticion));
    }
    return;
  }
  if (EXTERNOS_PERMITIDOS.includes(url.origin)) e.respondWith(copiaYActualiza(peticion));
});
