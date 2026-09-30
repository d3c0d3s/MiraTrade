/* MiraTrade on the web. Plain JavaScript on purpose: no build step, no framework to keep up with,
   and the thing it has to do is read an API and draw it.

   Two habits it keeps from the desktop, and both are about honesty rather than looks:
     - the honest note is always on screen, read from the latest report;
     - "not known" and "no" are drawn differently. A missing liquidity check or a missing earnings
       calendar says so; it never looks like a clean bill of health. */

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];

async function api(path, options) {
  const answer = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...options,
  });
  const body = await answer.json().catch(() => ({}));
  if (!answer.ok) throw new Error(body.detail || `${answer.status} ${answer.statusText}`);
  return body;
}

function toast(message, bad = false) {
  const box = $("#toast");
  box.textContent = message;
  box.classList.toggle("bad", bad);
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.hidden = true; }, bad ? 7000 : 3500);
}

const money = (v) => v == null ? "–" : (Math.abs(v) >= 1e6 ? `$${(v / 1e6).toFixed(1)}M`
  : Math.abs(v) >= 1e3 ? `$${(v / 1e3).toFixed(0)}k` : `$${Number(v).toFixed(2)}`);
const pct = (v) => v == null ? "–" : `${(v * 100).toFixed(1)} %`;
const num = (v) => v == null ? "–" : Number(v).toLocaleString("es-ES");

/* Colour is never the only difference: each kind carries its own shape, as on the desktop. */
const KIND = {
  "Insiders": ["insider", "◆", "Directivos"],
  "Options": ["options", "●", "Opciones"],
  "13D / 13G": ["ownership", "■", "13D / 13G"],
  "Congress": ["insider", "◆", "Congreso"],
};
const kindTag = (k) => {
  const [cls, shape, label] = KIND[k] || ["", "•", k];
  return `<span class="kind ${cls}">${shape} ${label}</span>`;
};

/* ── screens ───────────────────────────────────────────────────────────── */

function show(name, push = true) {
  if (!$(`#${CSS.escape(name)}.screen`)) name = "scanner";
  $$(".screen").forEach((s) => { s.hidden = s.id !== name; });
  $$("#nav button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.screen === name)));
  (LOAD[name] || (() => {}))();
  if (push && location.hash !== `#${name}`) history.pushState(null, "", `#${name}`);
  window.scrollTo({ top: 0 });
}

/* Deep links and the back button. Without this the address bar says one screen and the page shows
   another, which on a phone is how you end up reading yesterday's screen and not knowing it. */
addEventListener("hashchange", () => show((location.hash || "#scanner").slice(1), false));
addEventListener("popstate", () => show((location.hash || "#scanner").slice(1), false));

/* ── state of the data, and the jobs ───────────────────────────────────── */

async function refreshHealth() {
  try {
    const h = await api("/api/health");
    const pill = $("#fresh");
    pill.textContent = h.fresh;
    pill.classList.toggle("stale", h.stale);
    $("#stale").hidden = !h.stale;
    $("#stale-text").textContent = h.fresh;
  } catch (e) { $("#fresh").textContent = String(e.message); }
  try { $("#honesty").textContent = (await api("/api/honesty")).line; } catch { /* keep the last */ }
}

let watching = null;
async function refreshJobs() {
  const { running } = await api("/api/jobs");
  const pill = $("#job");
  if (running) {
    const last = running.log[running.log.length - 1] || "";
    pill.hidden = false;
    pill.textContent = `${running.kind}… ${last.slice(0, 60)}`;
    if (!watching) watching = setInterval(refreshJobs, 2000);
  } else {
    pill.hidden = true;
    if (watching) { clearInterval(watching); watching = null; refreshHealth(); reloadCurrent(); }
  }
  $$("button.primary").forEach((b) => { b.disabled = Boolean(running); });
}

async function startJob(kind, days) {
  try {
    await api("/api/jobs", { method: "POST", body: JSON.stringify({ kind, days: Number(days) }) });
    toast(kind === "download" ? "Descargando…" : "En marcha…");
    refreshJobs();
  } catch (e) { toast(e.message, true); }
}

function reloadCurrent() {
  const open = $$(".screen").find((s) => !s.hidden);
  if (open) (LOAD[open.id] || (() => {}))();
}

/* ── Scanner ───────────────────────────────────────────────────────────── */

let sources = [];
async function loadScanner() {
  if (!sources.length) {
    sources = await api("/api/sources");
    $("#source").innerHTML = sources.map((s) => `<option value="${s.key}">${s.label}</option>`).join("");
  }
  const summary = await api("/api/summary");
  $("#stored").textContent = summary.filter((s) => s.rows)
    .map((s) => `${s.label}: ${num(s.rows)}`).join("  ·  ");

  const q = new URLSearchParams({
    days: $("#f-days").value || 0, ticker: $("#f-ticker").value, text: $("#f-text").value,
    min_amount: $("#f-amount").value || 0,
    exclude_plan: $("#f-plan").checked, exclude_passive: $("#f-passive").checked, limit: 300,
  });
  const key = $("#source").value;
  const body = await api(`/api/scanner/${key}?${q}`);
  const columns = (sources.find((s) => s.key === key) || {}).columns || [];
  const shown = columns.filter((c) => c.kind !== "link");

  $("#scanner-table thead").innerHTML = `<tr>${shown.map((c) => `<th>${c.label}</th>`).join("")}</tr>`;
  $("#scanner-table tbody").innerHTML = body.rows.map((r) => `<tr>${shown.map((c) => {
    const v = r[c.name];
    const numeric = c.kind === "number" || c.kind === "money";
    return `<td class="${numeric ? "num" : ""}">${
      v == null ? "–" : c.kind === "money" ? money(v) : numeric ? num(v) : String(v)}</td>`;
  }).join("")}</tr>`).join("");

  $("#scanner-count").textContent = body.total === 0
    ? "Nada coincide con estos filtros. «Limpiar» los deja como estaban."
    : body.shown < body.total
      ? `${num(body.shown)} de ${num(body.total)} filas — afina los filtros para ver el resto`
      : `${num(body.total)} filas`;
}

/* ── Señales ───────────────────────────────────────────────────────────── */

const TIERS = [["all", "Todas"], ["mega", "Mega"], ["large", "Grande"], ["mid", "Media"],
               ["small", "Pequeña"], ["micro", "Micro"], ["mid_plus", "Media y mayores"]];

async function loadSignals() {
  if (!$("#ev-cap").options.length) {
    $("#ev-cap").innerHTML = TIERS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
  }
  const q = new URLSearchParams({ days: $("#ev-days").value || 30, cap_tier: $("#ev-cap").value, limit: 300 });
  const body = await api(`/api/events?${q}`);
  const list = $("#event-list");
  if (!body.rows.length) {
    list.innerHTML = `<p class="muted">Ningún evento en esos días con estos ajustes. Prueba con más
      días, un tramo de tamaño más amplio, o descarga más desde el Scanner.</p>`;
    $("#event-card").innerHTML = `<p class="muted">Elige un evento.</p>`;
    return;
  }
  list.innerHTML = body.rows.map((r) => `
    <button class="item" role="listitem" data-ticker="${r.ticker}" data-when="${r.signal_date}">
      <span class="row"><span class="ticker">${r.ticker}</span>
        <span class="when">${r.signal_date}</span></span>
      <span class="what">${r.what || ""}</span>
    </button>`).join("");
  $$("#event-list .item").forEach((b) => b.addEventListener("click", () => openEvent(b)));
  if (body.shown < body.total) {
    list.insertAdjacentHTML("beforeend",
      `<p class="muted small">${num(body.shown)} de ${num(body.total)}</p>`);
  }
  openEvent($("#event-list .item"));
}

async function openEvent(button) {
  if (!button) return;
  $$("#event-list .item").forEach((b) => b.removeAttribute("aria-current"));
  button.setAttribute("aria-current", "true");
  const card = $("#event-card");
  card.innerHTML = `<p class="muted">Cargando…</p>`;
  let c;
  try {
    c = await api(`/api/signal/${button.dataset.ticker}?signal_date=${button.dataset.when}`);
  } catch (e) { card.innerHTML = `<p class="warn">${e.message}</p>`; return; }

  const ev = c.evidence;
  const lq = c.tradeable;
  const ea = c.earnings;
  const ct = c.contract;

  card.innerHTML = `
    <h3>${c.ticker} <span class="muted small">${c.signal_date}</span></h3>
    <p>${c.kinds.map(kindTag).join("")}</p>
    <div class="block"><span class="label">Qué se presentó</span>
      <p>${c.what || "—"}</p></div>

    <div class="block"><span class="label">Evidencia</span>
      ${ev ? `<p>${ev.sentence}</p>
        <div class="grid">
          <div class="stat"><span class="label">objetivo</span><div class="v ok">${pct(ev.target)}</div></div>
          <div class="stat"><span class="label">stop</span><div class="v warn">${pct(ev.stop)}</div></div>
          <div class="stat"><span class="label">ninguno</span><div class="v">${pct(ev.neither)}</div></div>
          <div class="stat"><span class="label">casos</span><div class="v">${num(ev.n)}</div></div>
        </div>
        <p class="muted small">${ev.rules.length
          ? `Reglas validadas: ${ev.rules.join(", ")}.`
          : "Ninguna regla confirmada para este perfil. Trata la evidencia como historia, no como pronóstico."}</p>`
      : `<p class="muted">No hay reporte con eventos contra el que comparar. Ejecuta un análisis en Reportes.</p>`}
    </div>

    <div class="block"><span class="label">Contrato</span>
      ${ct ? `<div class="grid">
          <div class="stat"><span class="label">strike</span><div class="v">${money(ct.strike)}</div></div>
          <div class="stat"><span class="label">vence</span><div class="v">${ct.expiry}</div></div>
          <div class="stat"><span class="label">prima</span><div class="v">${money(ct.premium)}</div></div>
          <div class="stat"><span class="label">delta</span><div class="v">${ct.delta?.toFixed(2) ?? "–"}</div></div>
        </div>
        <p class="muted small">Objetivo ${money(ct.target)} · stop ${money(ct.stop)}</p>
        <button id="to-practice">Añadir a práctica</button>`
        : `<p class="muted">${c.contract_note}</p>`}
      <p class="muted small">${ct ? c.contract_note : ""}</p>
    </div>

    ${lq ? `<div class="block"><span class="label">¿Se puede operar?</span>
      <p class="${lq.ok ? "ok" : "warn"}">${lq.ok ? "" : "NO OPERABLE — "}${lq.reason}</p>
      ${lq.measured ? "" : `<p class="muted small">Sin cadena guardada para este contrato: esto mira
        la liquidez de la acción, que es una afirmación más débil.</p>`}</div>` : ""}

    ${ea ? `<div class="block"><span class="label">Resultados</span>
      <p class="${ea.date ? "warn" : "muted"}">${ea.note || "Sin informe dentro del vencimiento."}</p>
      ${ea.date ? `<p class="muted small">${ea.date}</p>` : ""}</div>` : ""}

    <p class="muted small">${c.honesty}</p>`;

  const add = $("#to-practice");
  if (add) add.addEventListener("click", async () => {
    add.disabled = true;
    try {
      const t = await api("/api/practice", {
        method: "POST",
        body: JSON.stringify({ ticker: c.ticker, signal_date: c.signal_date }),
      });
      toast(`Añadido: ${t.quantity} × ${t.ticker}. Sin dinero real.`);
    } catch (e) { toast(e.message, true); add.disabled = false; }
  });
}

/* ── Reportes ──────────────────────────────────────────────────────────── */

async function loadReports() {
  const list = await api("/api/reports");
  $("#report-list").innerHTML = list.length ? list.map((r) => `
    <button class="item" role="listitem" data-name="${r.name}">
      <span class="row"><span class="ticker">${r.name}</span>
        <span class="when">${r.start || ""}</span></span>
      <span class="what">${r.summary}</span>
    </button>`).join("")
    : `<p class="muted">Todavía no hay ningún análisis.</p>`;
  $$("#report-list .item").forEach((b) => b.addEventListener("click", async () => {
    $$("#report-list .item").forEach((o) => o.removeAttribute("aria-current"));
    b.setAttribute("aria-current", "true");
    const r = await api(`/api/reports/${encodeURIComponent(b.dataset.name)}`);
    $("#report-body").innerHTML = `<div class="markdown">${markdown(r.markdown)}</div>`;
  }));
  const first = $("#report-list .item");
  if (first) first.click();
}

/* A small Markdown renderer: headings, tables, bold and paragraphs, which is all an edge report
   uses. Everything is escaped first — the report is generated here, but a renderer that trusts its
   input is a habit that outlives the one file it was safe in. */
const escapeHtml = (s) => s.replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function markdown(text) {
  const lines = escapeHtml(text || "").split("\n");
  const out = [];
  let table = null;
  const flush = () => {
    if (!table) return;
    const [head, ...body] = table;
    out.push(`<table><thead><tr>${head.map((c) => `<th>${c}</th>`).join("")}</tr></thead>`
      + `<tbody>${body.map((r) => `<tr>${r.map((c) =>
        `<td class="${/^[-+$\d(]/.test(c.trim()) ? "num" : ""}">${c}</td>`).join("")}</tr>`).join("")}`
      + `</tbody></table>`);
    table = null;
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith("|")) {
      const cells = line.slice(1, line.endsWith("|") ? -1 : undefined).split("|").map((c) => c.trim());
      if (cells.every((c) => /^:?-{2,}:?$/.test(c))) continue;      // the ---|--- separator row
      (table = table || []).push(cells);
      continue;
    }
    flush();
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) { out.push(`<h${heading[1].length + 1}>${heading[2]}</h${heading[1].length + 1}>`); continue; }
    if (!line) continue;
    out.push(`<p>${line.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")}</p>`);
  }
  flush();
  return out.join("");
}

/* ── Práctica ──────────────────────────────────────────────────────────── */

async function loadPractice() {
  const p = await api("/api/practice");
  const s = p.summary;
  $("#practice-summary").textContent =
    `Cuenta ${money(p.equity)} · cerradas ${num(s.closed ?? 0)} · realizado ${money(s.realised ?? 0)}`
    + ` · abierto ${money(s.unrealised ?? 0)}`;

  /* The field names are what the journal stores; these are what a person reads. */
  const COLS = [["ticker", "Ticker"], ["kind", "Tipo"], ["quantity", "Cantidad"],
                ["entry", "Entrada"], ["stop", "Stop"], ["target", "Objetivo"],
                ["status", "Estado"], ["result", "Resultado"]];
  const cols = COLS.map(([k]) => k);
  $("#practice-table thead").innerHTML =
    `<tr>${COLS.map(([, label]) => `<th>${label}</th>`).join("")}<th></th></tr>`;
  $("#practice-table tbody").innerHTML = p.trades.length ? p.trades.map((t) => `
    <tr>${cols.map((c) => {
      const v = t[c];
      const cls = c === "result" ? (v > 0 ? "num up" : v < 0 ? "num down" : "num")
        : typeof v === "number" ? "num" : "";
      return `<td class="${cls}">${v == null ? "–"
        : typeof v === "number" && c !== "quantity" ? money(v) : String(v)}</td>`;
    }).join("")}
    <td>${t.status === "open" ? `<button class="ghost danger" data-close="${t.id}">Cerrar</button>` : ""}</td>
    </tr>`).join("")
    : `<tr><td colspan="${cols.length + 1}" class="muted">Todavía no has añadido ninguna operación.
        Ve a Señales, elige un evento y pulsa «Añadir a práctica».</td></tr>`;

  $$("[data-close]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      await api(`/api/practice/${b.dataset.close}/close`, { method: "POST", body: "{}" });
      toast("Cerrada."); loadPractice();
    } catch (e) { toast(e.message, true); b.disabled = false; }
  }));
}

/* ── Ajustes ───────────────────────────────────────────────────────────── */

function control(f) {
  const id = `set-${f.section}-${f.key}`;
  if (f.kind === "bool") {
    return `<input type="checkbox" id="${id}" ${f.value ? "checked" : ""}>`;
  }
  if (f.kind === "choice") {
    return `<select id="${id}">${f.choices.map((c) =>
      `<option value="${c.value}" ${c.value === f.value ? "selected" : ""}>${c.label}</option>`).join("")}</select>`;
  }
  if (f.kind === "text") return `<input type="text" id="${id}" value="${f.value ?? ""}">`;
  return `<input type="number" id="${id}" value="${f.value}" min="${f.low}" max="${f.high}"
            step="${f.kind === "integer" ? Math.max(1, f.step) : f.step}" inputmode="decimal">`;
}

function drawSettings(into, groups) {
  $(into).innerHTML = groups.map((g) => `
    <div class="group">
      <h3>${g.title}</h3><p class="muted small">${g.note}</p>
      ${g.fields.map((f) => `
        <div class="setting">
          <div class="top">
            <label for="set-${f.section}-${f.key}">${f.label}${f.suffix ? ` <span class="muted">(${f.suffix.trim()})</span>` : ""}</label>
            <span>${control(f)}
              <span class="changed">${f.changed ? `cambiado · por defecto ${f.default}` : ""}</span></span>
          </div>
          <div class="help">${f.help}</div>
        </div>`).join("")}
    </div>`).join("");

  groups.forEach((g) => g.fields.forEach((f) => {
    const input = $(`#set-${f.section}-${f.key}`);
    input.addEventListener("change", async () => {
      const value = f.kind === "bool" ? input.checked
        : f.kind === "choice" || f.kind === "text" ? input.value
          : f.kind === "integer" ? parseInt(input.value, 10) : parseFloat(input.value);
      try {
        await api("/api/settings", {
          method: "PUT",
          body: JSON.stringify({ section: f.section, key: f.key, value }),
        });
        toast(`${f.label} guardado`);
        loadSettings();
      } catch (e) { toast(e.message, true); }
    });
  }));
}

async function loadSettings() {
  const s = await api("/api/settings");
  /* On the form, not in a report: this is the moment somebody is about to try another
     configuration, which is the moment the number means something. */
  $("#attempts").textContent = s.multiple_testing;
  $("#attempts-box").classList.toggle("steady", s.attempts <= 5);
  drawSettings("#settings-rules", s.rules);
  drawSettings("#settings-operation", s.operation);
}

/* ── wiring ────────────────────────────────────────────────────────────── */

const LOAD = {
  scanner: loadScanner, signals: loadSignals, reports: loadReports,
  practice: loadPractice, settings: loadSettings,
};

function guard(fn) {
  return async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };
}
Object.keys(LOAD).forEach((k) => { LOAD[k] = guard(LOAD[k]); });

$$("#nav button").forEach((b) => b.addEventListener("click", () => show(b.dataset.screen)));
$$("[data-goto]").forEach((b) => b.addEventListener("click", () => show(b.dataset.goto)));

$("#download").addEventListener("click", () => startJob("download", $("#fetch-days").value));
$("#search").addEventListener("click", () => startJob("search", $("#ev-days").value));
$("#analyse").addEventListener("click", () => startJob("analysis", $("#an-days").value));

["#source", "#f-days", "#f-ticker", "#f-text", "#f-amount", "#f-plan", "#f-passive"]
  .forEach((s) => $(s).addEventListener("change", () => LOAD.scanner()));
$("#clear-filters").addEventListener("click", () => {
  $("#f-days").value = 30; $("#f-ticker").value = ""; $("#f-text").value = "";
  $("#f-amount").value = 0; $("#f-plan").checked = false; $("#f-passive").checked = false;
  LOAD.scanner();
});
["#ev-days", "#ev-cap"].forEach((s) => $(s).addEventListener("change", () => LOAD.signals()));

refreshHealth();
refreshJobs().catch(() => {});
show((location.hash || "#scanner").slice(1), false);
setInterval(refreshHealth, 60000);
