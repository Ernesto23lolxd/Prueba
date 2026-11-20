// STOCK · app web (JavaScript puro)
const API = ""; // mismo servidor que sirve la página

const $ = (id) => document.getElementById(id);

// Seguridad: escapar todo dato dinámico antes de meterlo en innerHTML
function escapeHTML(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
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
    .map((a) => (a.ok ? `✔ ${escapeHTML(a.tipo)} · ${escapeHTML(a.producto)} ${a.ahora !== undefined ? `(${escapeHTML(a.antes)} → ${escapeHTML(a.ahora)})` : ""}`
                      : `✖ ${escapeHTML(a.producto)}: ${escapeHTML(a.error)}`))
    .join("<br>");
  agregarMensaje("bot", data.respuesta, detalle);
  hablar(data.respuesta);
  ultimosCambios = new Set((data.acciones || []).map((a) => a.producto));
  await cargarInventario();
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
    <span class="cant">${escapeHTML(p.cantidad)} ${escapeHTML(p.unidad)}</span>
    <span class="min">${p.se_acaba_texto ? `se acaba ${escapeHTML(p.se_acaba_texto)}` : `mín ${escapeHTML(p.minimo)}`}</span>`;
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
  const r = await fetch(`${API}/api/prediccion`); // inventario + cuándo se acaba cada producto
  pintarInventario(await r.json());
  cargarListaCompras();
}

// ---------------------------------------------------------------- Lista de compras
const pesos = (n) => n.toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });

async function cargarListaCompras() {
  const r = await fetch(`${API}/api/lista-compras`);
  const lista = await r.json();
  const ul = $("listaCompras");
  if (!lista.items.length) {
    ul.replaceChildren(Object.assign(document.createElement("li"), { textContent: "Nada urgente por comprar 👌" }));
  } else {
    ul.replaceChildren(
      ...lista.items.map((i) => {
        const li = document.createElement("li");
        li.className = i.urgencia;
        const unidad = i.unidad === "kg" ? "kg" : "pzas";
        li.innerHTML = `<span><b></b> <span class="nombre"></span></span><span class="cuando"></span>`;
        li.querySelector("b").textContent = `${i.cantidad} ${unidad}`;
        li.querySelector(".nombre").textContent = i.nombre;
        li.querySelector(".cuando").textContent = `se acaba ${i.se_acaba}`;
        return li;
      })
    );
  }
  $("totalCompras").textContent = lista.items.length ? `Valor aprox. (a precio de venta): ${pesos(lista.total_estimado)}` : "";
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

// ---------------------------------------------------------------- Importar Excel
const nombresCampo = { nombre: "Producto", cantidad: "Existencia", unidad: "Unidad", precio: "Precio venta",
                       costo: "Costo", minimo: "Mínimo", categoria: "Categoría" };

async function enviarExcel(archivo, confirmar) {
  const datos = new FormData();
  datos.append("archivo", archivo);
  datos.append("confirmar", confirmar ? "true" : "false");
  const r = await fetch(`${API}/api/importar`, { method: "POST", body: datos });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "No pude leer el archivo");
  return data;
}

$("inputExcel").addEventListener("change", async (e) => {
  const archivo = e.target.files[0];
  if (!archivo) return;
  const caja = $("vistaPrevia");
  caja.textContent = "Leyendo tu Excel…";
  try {
    const d = await enviarExcel(archivo, false);
    const columnas = Object.entries(d.columnas)
      .map(([campo, col]) => `<li><b></b> ← columna “<span></span>”</li>`).join("");
    caja.innerHTML = `
      <p>Encontré <b>${d.productos.length}</b> productos: <b>${d.nuevos}</b> nuevos y <b>${d.actualizados}</b> que ya tenías.</p>
      <p class="ayuda">Así entendí tus columnas (${d.metodo === "ia" ? "con IA" : "por palabras clave"}):</p>
      <ul class="columnas">${columnas}</ul>
      <div class="tabla-scroll"><table><thead><tr><th>Producto</th><th>Hay</th><th>Precio</th><th></th></tr></thead><tbody></tbody></table></div>
      ${d.ignoradas.length ? `<p class="ayuda">Ignoré ${d.ignoradas.length} filas sin producto (títulos o totales).</p>` : ""}
      <button class="boton" id="btnConfirmarExcel">✅ Importar ${d.productos.length} productos</button>`;
    // Textos del archivo con textContent (seguro ante contenido raro en el Excel)
    caja.querySelectorAll(".columnas li").forEach((li, i) => {
      const [campo, col] = Object.entries(d.columnas)[i];
      li.querySelector("b").textContent = nombresCampo[campo] || campo;
      li.querySelector("span").textContent = col;
    });
    caja.querySelector("tbody").replaceChildren(...d.productos.map((p) => {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td></td><td></td><td></td><td><span class='etiqueta'></span></td>";
      tr.children[0].textContent = p.nombre;
      tr.children[1].textContent = `${p.cantidad} ${p.unidad}`;
      tr.children[2].textContent = p.precio != null ? pesos(p.precio) : "—";
      const et = tr.querySelector(".etiqueta");
      et.textContent = p.accion === "nuevo" ? "nuevo" : `antes ${p.antes}`;
      et.classList.toggle("nuevo", p.accion === "nuevo");
      return tr;
    }));
    $("btnConfirmarExcel").addEventListener("click", async () => {
      caja.textContent = "Guardando…";
      try {
        const g = await enviarExcel(archivo, true);
        caja.textContent = `✅ Listo: ${g.nuevos} productos nuevos y ${g.actualizados} actualizados.`;
        hablar(`Listo, importé ${g.productos.length} productos de tu Excel.`);
        cargarInventario();
        cargarMovimientos();
      } catch (err) {
        caja.textContent = `❌ ${err.message}`;
      }
    });
  } catch (err) {
    caja.textContent = `❌ ${err.message}`;
  } finally {
    e.target.value = ""; // permite volver a subir el mismo archivo
  }
});

cargarInventario();
cargarMovimientos();
