"use strict";

const $ = (s) => document.querySelector(s);
const KEY = "ancmed_game_id";

const el = {
  setup: $("#setup"), setupError: $("#setup-error"),
  game: $("#game"), status: $("#status"), newGameBtn: $("#new-game-btn"),
  mapSelect: $("#map-select"), powerSelect: $("#power-select"),
  difficultySelect: $("#difficulty-select"), mapNote: $("#map-note"),
  startBtn: $("#start-btn"), mapHolder: $("#map-holder"), mapHint: $("#map-hint"),
  orderMenu: $("#order-menu"),
  banner: $("#banner"), scTable: $("#sc-table"), winNote: $("#win-note"),
  ordersCard: $("#orders-card"), ordersTitle: $("#orders-title"),
  ordersHint: $("#orders-hint"), ordersList: $("#orders-list"), submitBtn: $("#submit-btn"),
  timebar: $("#timebar"), histPrev: $("#hist-prev"), histNext: $("#hist-next"),
  histSlider: $("#hist-slider"), histLabel: $("#hist-label"),
  historyNote: $("#history-note"), historyNoteLabel: $("#history-note-label"),
  returnCurrent: $("#return-current"),
  resultsCard: $("#results-card"), resultsBody: $("#results-body"),
  overlay: $("#overlay"), sourceLink: $("#source-link"),
};

const ACTION_LABEL = {
  hold: "Hold",
  move: "Move to…",
  support_hold: "Support hold…",
  support_move: "Support move…",
  convoy: "Convoy…",
  retreat: "Retreat to…",
  disband: "Disband",
  build_army: "Build army",
  build_fleet: "Build fleet",
  waive: "Waive (no build)",
  keep: "Keep unit",
};

let MAPS = [];
let state = null;        // latest live state
let viewingIndex = null; // history index being viewed, or null = current

async function api(path, opts) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

const title = (s) => (s ? s[0].toUpperCase() + s.slice(1).toLowerCase() : s);

/* ---------------------------------------------------------------- setup --- */
async function initSetup() {
  const data = await api("/api/maps");
  MAPS = data.maps;
  if (data.source_url) el.sourceLink.href = data.source_url;
  el.mapSelect.innerHTML = MAPS.map((m) => `<option value="${m.name}">${m.label}</option>`).join("");
  el.difficultySelect.innerHTML = data.difficulties
    .map((d) => `<option value="${d}"${d === "medium" ? " selected" : ""}>${title(d)}</option>`)
    .join("");
  el.mapSelect.onchange = fillPowers;
  fillPowers();
}

function fillPowers() {
  const map = MAPS.find((m) => m.name === el.mapSelect.value);
  el.powerSelect.innerHTML = map.powers.map((p) => `<option value="${p}">${title(p)}</option>`).join("");
  el.mapNote.textContent = `${map.powers.length} powers. You play one, bots play the rest.`;
}

el.startBtn.onclick = async () => {
  el.startBtn.disabled = true;
  el.setupError.hidden = true;
  try {
    const s = await api("/api/games", {
      method: "POST",
      body: JSON.stringify({
        map_name: el.mapSelect.value,
        power: el.powerSelect.value,
        difficulty: el.difficultySelect.value,
      }),
    });
    localStorage.setItem(KEY, s.game_id);
    setState(s);
  } catch (err) {
    el.setupError.textContent = err.message;
    el.setupError.hidden = false;
  } finally {
    el.startBtn.disabled = false;
  }
};

el.newGameBtn.onclick = () => {
  localStorage.removeItem(KEY);
  el.game.hidden = true;
  el.setup.hidden = false;
  el.newGameBtn.hidden = true;
  el.status.textContent = "";
};

/* ----------------------------------------------------------- rendering --- */
function powerColors(svgText) {
  const colors = {};
  const re = /\.([a-z]+)\s*\{[^}]*fill\s*:\s*([^;]+)[;}]/g;
  let m;
  while ((m = re.exec(svgText))) {
    if (!m[1].startsWith("unit") && !m[1].startsWith("province") && !colors[m[1].toUpperCase()]) {
      colors[m[1].toUpperCase()] = m[2].trim();
    }
  }
  return colors;
}

function setState(s) {
  state = s;
  viewingIndex = null;
  resetSelection();
  el.setup.hidden = true;
  el.game.hidden = false;
  el.newGameBtn.hidden = false;
  el.sourceLink.href = s.source_url || "#";

  el.status.textContent = `${title(s.map_name)} — you are ${title(s.your_power)} · ${title(
    s.difficulty
  )} bots · ${s.phase_long}`;

  renderSidebar(s);
  renderTimebar(s);
  showBoard(s.svg);
  renderOrders(s);
  renderResults(s.last_phase);
}

function showBoard(svg) {
  el.mapHolder.innerHTML = svg;
  markOrderableProvinces();
  reapplySelectionHighlight();
}

function markOrderableProvinces() {
  const orderable = state && !state.is_done && viewingIndex === null;
  el.mapHolder.classList.toggle("pickable", !!orderable);
  if (!orderable) return;
  const svg = el.mapHolder.querySelector("svg");
  if (!svg) return;
  for (const loc of Object.keys(state.orderable)) {
    const node = svgNodeFor(loc);
    if (node) node.setAttribute("data-orderable", "1");
  }
}

function renderSidebar(s) {
  const colors = powerColors(s.svg);
  el.scTable.innerHTML = s.powers
    .map((pw) => {
      const n = s.sc_counts[pw] || 0;
      const out = s.eliminated.includes(pw);
      const cls = [pw === s.your_power ? "you" : "", out ? "out" : ""].join(" ").trim();
      const sw = colors[pw] ? `<span class="swatch" style="background:${colors[pw]}"></span>` : "";
      return `<tr class="${cls}"><td>${sw}${title(pw)}</td><td class="n">${n}</td></tr>`;
    })
    .join("");
  el.winNote.textContent = s.win_centers ? `${s.win_centers} centres to win.` : "";

  if (s.is_done) {
    el.banner.hidden = false;
    el.banner.textContent = endText(s);
  } else {
    el.banner.hidden = true;
  }
}

/* ------------------------------------------------------------- timebar --- */
function renderTimebar(s) {
  const n = s.history.length; // index n == the live position
  if (n === 0) {
    el.timebar.hidden = true;
    return;
  }
  el.timebar.hidden = false;
  el.histSlider.max = String(n);
  el.histSlider.value = String(viewingIndex === null ? n : viewingIndex);
  el.histLabel.textContent =
    viewingIndex === null ? "Current turn" : s.history[viewingIndex].label;
}

el.histSlider.oninput = () => {
  const v = Number(el.histSlider.value);
  gotoPhase(v >= state.history.length ? null : v);
};
el.histPrev.onclick = () => {
  const cur = viewingIndex === null ? state.history.length : viewingIndex;
  if (cur > 0) gotoPhase(cur - 1);
};
el.histNext.onclick = () => {
  const cur = viewingIndex === null ? state.history.length : viewingIndex;
  if (cur < state.history.length) gotoPhase(cur + 1 >= state.history.length ? null : cur + 1);
};
el.returnCurrent.onclick = () => gotoPhase(null);

async function gotoPhase(index) {
  resetSelection();
  if (index === null) {
    viewingIndex = null;
    showBoard(state.svg);
    renderTimebar(state);
    el.historyNote.hidden = true;
    el.ordersCard.hidden = state.is_done;
    renderResults(state.last_phase);
    return;
  }
  try {
    const p = await api(`/api/games/${state.game_id}/phase/${index}`);
    viewingIndex = index;
    showBoard(p.svg);
    renderTimebar(state);
    el.historyNote.hidden = false;
    el.historyNoteLabel.textContent = p.label;
    el.ordersCard.hidden = true;
    renderResults(p);
  } catch (err) {
    alert(err.message);
  }
}

/* -------------------------------------------------------------- orders --- */
function renderOrders(s) {
  el.historyNote.hidden = true;
  if (s.is_done) {
    el.ordersCard.hidden = true;
    return;
  }
  el.ordersCard.hidden = false;

  const locs = Object.keys(s.orderable).sort();
  el.ordersTitle.textContent =
    { M: "Your orders", R: "Retreats", A: "Builds & disbands" }[s.phase_type] || "Orders";
  el.mapHint.hidden = !locs.length;

  if (s.phase_type === "A" && s.builds_allowed != null) {
    el.ordersHint.textContent = s.builds_allowed
      ? `You may build ${s.builds_allowed}. Unused centres are waived.`
      : "";
  } else if (s.phase_type === "R") {
    el.ordersHint.textContent = "Pick where each dislodged unit goes.";
  } else {
    el.ordersHint.textContent = "";
  }

  if (!locs.length) {
    el.ordersList.innerHTML = `<p class="note">Nothing for you to order — submit to continue.</p>`;
    el.submitBtn.textContent = "Continue";
  } else {
    el.submitBtn.textContent = "Submit orders";
    el.ordersList.innerHTML = "";
    for (const loc of locs) {
      el.ordersList.appendChild(orderRow(s.orderable[loc], s.phase_type));
    }
  }
  el.submitBtn.onclick = submit;
}

function populateSecondary(secondary, action) {
  const list = action.targets || action.moves;
  if (list) {
    secondary.hidden = false;
    secondary.innerHTML = list
      .map((t) => `<option value="${encodeURIComponent(t.order)}">${t.label}</option>`)
      .join("");
  } else {
    secondary.hidden = true;
    secondary.innerHTML = "";
  }
}

function orderRow(node, phaseType) {
  const row = document.createElement("div");
  row.className = "order-row";
  row.dataset.loc = node.loc;

  const label = document.createElement("label");
  label.textContent = node.label;
  row.appendChild(label);

  const selects = document.createElement("div");
  selects.className = "selects";
  row.appendChild(selects);

  const primary = document.createElement("select");
  primary.className = "primary";
  const acts = node.actions;
  primary.innerHTML = acts
    .map((a, i) => `<option value="${i}">${ACTION_LABEL[a.type] || a.type}</option>`)
    .join("");
  selects.appendChild(primary);

  const secondary = document.createElement("select");
  secondary.className = "secondary";
  selects.appendChild(secondary);

  primary.onchange = () => {
    populateSecondary(secondary, acts[Number(primary.value)]);
    onOrderRowChanged();
  };
  secondary.onchange = onOrderRowChanged;

  // default selection
  let def = 0;
  const want =
    phaseType === "A"
      ? ["waive", "keep"]
      : phaseType === "R"
      ? ["retreat", "disband"]
      : ["hold"];
  for (const w of want) {
    const idx = acts.findIndex((a) => a.type === w);
    if (idx >= 0) { def = idx; break; }
  }
  primary.value = String(def);
  populateSecondary(secondary, acts[def]);

  return row;
}

function resolveRow(row) {
  const primary = row.querySelector(".primary");
  const secondary = row.querySelector(".secondary");
  const node = state.orderable[row.dataset.loc];
  const a = node.actions[Number(primary.value)];
  if (a.type === "keep") return null;
  if (a.order !== undefined && a.order !== null && !a.targets && !a.moves) {
    return a.order || null;
  }
  return secondary.value ? decodeURIComponent(secondary.value) : null;
}

function collectOrders() {
  return [...el.ordersList.querySelectorAll(".order-row")].map(resolveRow).filter(Boolean);
}

/** Set a unit's dropdown row to match `order` (from a map click), without
 * assuming which action/target it resolves to - mirrors resolveRow() in reverse. */
function applyOrderToRow(loc, order) {
  const row = el.ordersList.querySelector(`.order-row[data-loc="${cssEscape(loc)}"]`);
  const node = state.orderable[loc];
  if (!row || !node) return;
  const primary = row.querySelector(".primary");
  const secondary = row.querySelector(".secondary");
  for (let i = 0; i < node.actions.length; i++) {
    const a = node.actions[i];
    const list = a.targets || a.moves;
    if (list) {
      const hit = list.find((t) => t.order === order);
      if (hit) {
        primary.value = String(i);
        populateSecondary(secondary, a);
        secondary.value = encodeURIComponent(order);
        return;
      }
    } else if ((a.order || null) === (order || null)) {
      primary.value = String(i);
      populateSecondary(secondary, a);
      return;
    }
  }
}

function cssEscape(s) {
  return window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/["\\]/g, "\\$&");
}

let previewTimer = null;
function onOrderRowChanged() {
  if (!state || viewingIndex !== null) return;
  if (previewTimer) clearTimeout(previewTimer);
  previewTimer = setTimeout(refreshPreview, 50);
}

async function refreshPreview() {
  if (!state || viewingIndex !== null) return;
  try {
    const res = await api(`/api/games/${state.game_id}/preview`, {
      method: "POST",
      body: JSON.stringify({ orders: collectOrders() }),
    });
    el.mapHolder.innerHTML = res.svg;
    markOrderableProvinces();
    reapplySelectionHighlight();
  } catch (_) {
    // a stale preview render isn't worth interrupting the player over
  }
}

async function submit() {
  el.overlay.hidden = false;
  resetSelection();
  const orders = collectOrders();
  try {
    const s = await api(`/api/games/${state.game_id}/orders`, {
      method: "POST",
      body: JSON.stringify({ orders }),
    });
    setState(s);
  } catch (err) {
    alert(err.message);
  } finally {
    el.overlay.hidden = true;
  }
}

/* ------------------------------------------------- click-to-order on map --- */
// `selection` walks a unit through: pick an action -> (if it needs a target)
// pick a destination, or for support-move/convoy, pick the supported unit
// then its destination. Every step is resolvable either by clicking the
// board or by clicking the floating menu's list - same data, two inputs.
let selection = null;
// null
// | { loc, mode: "menu" }
// | { loc, mode: "target", action }
// | { loc, mode: "from",   action }
// | { loc, mode: "to",     action, from }

function svgNodeFor(code) {
  const svg = el.mapHolder.querySelector("svg");
  return svg ? svg.querySelector(`[id="_${code.toLowerCase()}"]`) : null;
}

function resetSelection() {
  selection = null;
  hideMenu();
  clearHighlight();
}

function clearHighlight() {
  const svg = el.mapHolder.querySelector("svg");
  if (!svg) return;
  svg.querySelectorAll(".hl-selected, .hl-target").forEach((n) =>
    n.classList.remove("hl-selected", "hl-target")
  );
}

function clearTargetHighlight() {
  const svg = el.mapHolder.querySelector("svg");
  if (svg) svg.querySelectorAll(".hl-target").forEach((n) => n.classList.remove("hl-target"));
}

function highlight(cls, codes) {
  for (const code of codes) {
    const n = svgNodeFor(code);
    if (n) n.classList.add(cls);
  }
}

function reapplySelectionHighlight() {
  if (!selection) return;
  highlight("hl-selected", [selection.loc]);
  if (selection.mode === "target") {
    highlight("hl-target", selection.action.targets.map((t) => t.prov));
  } else if (selection.mode === "from") {
    highlight("hl-target", [...new Set(selection.action.moves.map((m) => m.from))]);
  } else if (selection.mode === "to") {
    highlight(
      "hl-target",
      selection.action.moves.filter((m) => m.from === selection.from).map((m) => m.to)
    );
  }
}

el.mapHolder.addEventListener("click", (event) => {
  if (!state || state.is_done || viewingIndex !== null) return;
  const hit = event.target.closest && event.target.closest('[id^="_"]');
  if (!hit) return;
  handleProvinceClick(hit.id.slice(1).toUpperCase(), event);
});

document.addEventListener("click", (event) => {
  if (!selection) return;
  if (el.orderMenu.contains(event.target) || el.mapHolder.contains(event.target)) return;
  resetSelection();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && selection) resetSelection();
});

function handleProvinceClick(code, event) {
  if (selection && (selection.mode === "target" || selection.mode === "from" || selection.mode === "to")) {
    if (resolveClickAgainstSelection(code)) return;
  }
  if (Object.prototype.hasOwnProperty.call(state.orderable, code)) {
    selectUnit(code, event);
  } else {
    resetSelection();
  }
}

function resolveClickAgainstSelection(code) {
  if (selection.mode === "target") {
    const hit = selection.action.targets.find((t) => t.prov === code);
    if (hit) { finalizeOrder(selection.loc, hit.order); return true; }
    return false;
  }
  if (selection.mode === "from") {
    const matches = selection.action.moves.filter((m) => m.from === code);
    if (matches.length) {
      selection = { ...selection, mode: "to", from: code };
      clearTargetHighlight();
      highlight("hl-target", matches.map((m) => m.to));
      showToMenu(matches);
      return true;
    }
    return false;
  }
  if (selection.mode === "to") {
    const hit = selection.action.moves.find((m) => m.from === selection.from && m.to === code);
    if (hit) { finalizeOrder(selection.loc, hit.order); return true; }
    return false;
  }
  return false;
}

function selectUnit(loc, event) {
  clearHighlight();
  selection = { loc, mode: "menu" };
  highlight("hl-selected", [loc]);
  showActionMenu(state.orderable[loc], event);
}

function chooseAction(action) {
  if (!selection) return;
  if (!action.targets && !action.moves) {
    finalizeOrder(selection.loc, action.order || null);
    return;
  }
  if (action.targets) {
    selection = { ...selection, mode: "target", action };
    clearTargetHighlight();
    highlight("hl-target", action.targets.map((t) => t.prov));
    showTargetMenu(action.targets);
    return;
  }
  selection = { ...selection, mode: "from", action };
  clearTargetHighlight();
  highlight("hl-target", [...new Set(action.moves.map((m) => m.from))]);
  showFromMenu(action.moves);
}

function finalizeOrder(loc, order) {
  applyOrderToRow(loc, order);
  resetSelection();
  onOrderRowChanged();
}

/* ---- floating menu ------------------------------------------------------ */
function hideMenu() {
  el.orderMenu.hidden = true;
  el.orderMenu.innerHTML = "";
}

function menuFrame(titleText) {
  el.orderMenu.innerHTML = "";
  const t = document.createElement("div");
  t.className = "menu-title";
  t.textContent = titleText;
  el.orderMenu.appendChild(t);
  return el.orderMenu;
}

function menuButton(text, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = text;
  // stopPropagation matters here: onClick() typically rebuilds #order-menu's
  // innerHTML (clearing this very button out of the DOM) or hides the menu
  // entirely before this click finishes bubbling. If it reached the
  // document-level "click outside closes the menu" listener afterwards,
  // `orderMenu.contains(event.target)` would see the now-detached button and
  // read as "outside", re-cancelling the selection this same click just made.
  btn.onclick = (event) => {
    event.stopPropagation();
    onClick();
  };
  el.orderMenu.appendChild(btn);
}

function menuBackButton() {
  menuButton("← Start over", () => selectUnit(selection.loc, null));
  el.orderMenu.lastElementChild.classList.add("menu-back");
}

function showActionMenu(node, event) {
  menuFrame(node.label);
  for (const action of node.actions) {
    menuButton(ACTION_LABEL[action.type] || action.type, () => chooseAction(action));
  }
  positionMenu(event);
}

function showTargetMenu(targets) {
  menuFrame("Choose a destination");
  for (const t of targets) {
    menuButton(t.label, () => finalizeOrder(selection.loc, t.order));
  }
  menuBackButton();
  positionMenu(null);
}

function showFromMenu(moves) {
  menuFrame("Support / convoy which unit?");
  const seen = new Set();
  for (const m of moves) {
    if (seen.has(m.from)) continue;
    seen.add(m.from);
    menuButton(m.label.split(" → ")[0], () => resolveClickAgainstSelection(m.from));
  }
  menuBackButton();
  positionMenu(null);
}

function showToMenu(moves) {
  menuFrame("...moving to?");
  for (const m of moves) {
    menuButton(m.label.split(" → ")[1] || m.label, () => finalizeOrder(selection.loc, m.order));
  }
  menuBackButton();
  positionMenu(null);
}

function positionMenu(event) {
  const menu = el.orderMenu;
  menu.hidden = false;
  if (event) {
    const pad = 8;
    let x = event.clientX + pad;
    let y = event.clientY + pad;
    const rect = menu.getBoundingClientRect();
    if (x + rect.width > window.innerWidth - pad) x = window.innerWidth - rect.width - pad;
    if (y + rect.height > window.innerHeight - pad) y = window.innerHeight - rect.height - pad;
    menu.style.left = `${Math.max(pad, x)}px`;
    menu.style.top = `${Math.max(pad, y)}px`;
  }
}

/* ------------------------------------------------------------- results --- */
function renderResults(data) {
  if (!data) {
    el.resultsCard.hidden = true;
    return;
  }
  el.resultsCard.hidden = false;
  el.resultsCard.querySelector("summary").textContent = `${data.phase} orders`;
  const names = state.province_names || {};
  const pretty = (o) =>
    o.replace(/\b([A-Z]{3})(\/[NSEW]C)?\b/g, (m, c, coast) =>
      names[c] ? names[c] + (coast ? " " + coast.slice(1) : "") : m
    );
  el.resultsBody.innerHTML = Object.keys(data.orders)
    .sort()
    .map((pw) => {
      const lines = data.orders[pw]
        .map((o) => {
          const unit = o.split(" ").slice(0, 2).join(" ");
          const tags = (data.results && data.results[unit]) || [];
          const failed = tags.some((t) => /bounce|void|no convoy|dislodged|cut/.test(t));
          const suf = tags.length ? ` (${tags.join(", ")})` : "";
          return `<span class="o${failed ? " fail" : ""}">${pretty(o)}${suf}</span>`;
        })
        .join("");
      return `<div class="pw">${title(pw)}</div>${lines || '<span class="o">—</span>'}`;
    })
    .join("");
}

function endText(s) {
  const winners = (s.outcome || []).slice(1);
  if (winners.length === 1) return `Game over — ${title(winners[0])} wins.`;
  if (winners.length > 1) return `Game over — draw between ${winners.map(title).join(", ")}.`;
  return "Game over.";
}

/* ---------------------------------------------------------------- boot --- */
(async function boot() {
  await initSetup();
  const saved = localStorage.getItem(KEY);
  if (saved) {
    try {
      setState(await api(`/api/games/${saved}`));
      return;
    } catch (_) {
      localStorage.removeItem(KEY);
    }
  }
  el.game.hidden = true;
  el.setup.hidden = false;
})();
