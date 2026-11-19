// Surtí · app web (JavaScript puro)
const API = ""; // mismo servidor que sirve la página

const $ = (id) => document.getElementById(id);
const btnMic = $("btnMic");
const estadoMic = $("estadoMic");
const chat = $("chat");

let grabadora = null;
let trozos = [];
let ultimosCambios = new Set();

// ---------------------------------------------------------------- Voz
btnMic.addEventListener("click", async () => {
  if (grabadora && grabadora.state === "recording") {
    grabadora.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    grabadora = new MediaRecorder(stream);
    trozos = [];
    grabadora.ondataavailable = (e) => trozos.push(e.data);
    grabadora.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      btnMic.classList.remove("grabando");
      const blob = new Blob(trozos, { type: grabadora.mimeType || "audio/webm" });
      await enviarAudio(blob);
    };
    grabadora.start();
    btnMic.classList.add("grabando");
    estadoMic.textContent = "Escuchando… toca otra vez para terminar";
  } catch (err) {
    estadoMic.textContent =
      "No pude usar el micrófono. Abre la app en http://localhost o con HTTPS, o escribe abajo.";
    console.error(err);
  }
});

async function enviarAudio(blob) {
  estadoMic.textContent = "Pensando…";
  btnMic.disabled = true;
  const datos = new FormData();
  const ext = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
  datos.append("audio", blob, `voz.${ext}`);
  try {
    const r = await fetch(`${API}/api/voz`, { method: "POST", body: datos });
    await manejarRespuesta(r);
  } finally {
    btnMic.disabled = false;
    estadoMic.textContent = "Toca y habla";
  }
}

// ---------------------------------------------------------------- Texto (respaldo)
$("formTexto").addEventListener("submit", async (e) => {
  e.preventDefault();
  const texto = $("inputTexto").value.trim();
  if (!texto) return;
  $("inputTexto").value = "";
  const r = await fetch(`${API}/api/texto`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ texto }),
  });
  await manejarRespuesta(r);
});

async function manejarRespuesta(r) {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    agregarMensaje("bot error", data.detail || "Ocurrió un error");
    return;
  }
  agregarMensaje("usuario", data.transcripcion);
  const detalle = (data.acciones || [])
    .map((a) => (a.ok ? `✔ ${a.tipo} · ${a.producto} ${a.ahora !== undefined ? `(${a.antes} → ${a.ahora})` : ""}`
                      : `✖ ${a.producto}: ${a.error}`))
    .join("<br>");
  agregarMensaje("bot", data.respuesta, detalle);
  hablar(data.respuesta);
  ultimosCambios = new Set((data.acciones || []).map((a) => a.producto));
  pintarInventario(data.inventario);
  cargarMovimientos();
}

function agregarMensaje(clase, texto, detalle = "") {
  const div = document.createElement("div");
  div.className = `msg ${clase}`;
  div.textContent = texto;
  if (detalle) {
    const s = document.createElement("small");
    s.innerHTML = detalle;
    div.appendChild(s);
  }
  chat.prepend(div);
}

function hablar(texto) {
  if (!texto || !("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(texto);
  u.lang = "es-MX";
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

// ---------------------------------------------------------------- Inventario
function tarjetaProducto(p) {
  const div = document.createElement("div");
  div.className = `prod ${p.estado}${ultimosCambios.has(p.nombre) ? " cambio" : ""}`;
  div.innerHTML = `
    <span class="punto"></span>
    <span class="nombre"></span>
    <span class="cant">${p.cantidad} ${p.unidad}</span>
    <span class="min">mín ${p.minimo}</span>`;
  div.querySelector(".nombre").textContent = p.nombre;
  return div;
}

function pintarInventario(productos) {
  const orden = { agotado: 0, bajo: 1, atencion: 2, ok: 3 };
  productos.sort((a, b) => orden[a.estado] - orden[b.estado] || a.nombre.localeCompare(b.nombre));
  $("inventario").replaceChildren(...productos.map(tarjetaProducto));
  const alertas = productos.filter((p) => p.estado === "bajo" || p.estado === "agotado");
  $("alertas").replaceChildren(
    ...(alertas.length ? alertas.map(tarjetaProducto) : [Object.assign(document.createElement("p"), {
      className: "vacio", textContent: "Todo bien surtido 👌" })])
  );
}

async function cargarInventario() {
  const r = await fetch(`${API}/api/inventario`);
  pintarInventario(await r.json());
}

async function cargarMovimientos() {
  const r = await fetch(`${API}/api/movimientos?limite=10`);
  const lista = await r.json();
  $("movimientos").replaceChildren(
    ...lista.map((m) => {
      const li = document.createElement("li");
      li.textContent = `${m.fecha.slice(11, 16)} · ${m.tipo} · ${m.cantidad} ${m.unidad} de ${m.nombre}`;
      return li;
    })
  );
}

cargarInventario();
cargarMovimientos();
