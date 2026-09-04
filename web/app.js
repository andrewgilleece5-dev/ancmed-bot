"use strict";

const $ = (s) => document.querySelector(s);
const KEY = "ancmed_game_id";

const el = {
  setup: $("#setup"), setupError: $("#setup-error"),
  game: $("#game"), status: $("#status"), newGameBtn: $("#new-game-btn"),
  mapSelect: $("#map-select"), powerSelect: $("#power-select"),
  difficultySelect: $("#difficulty-select"), mapNote: $("#map-note"),
  startBtn: $("#start-btn"), mapHolder: $("#map-holder"),
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
let state = null;      // latest live state
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

  function refresh() {
    const a = acts[Number(primary.value)];
    const list = a.targets || a.moves;
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
  primary.onchange = refresh;

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
  refresh();

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

async function submit() {
  el.overlay.hidden = false;
  const orders = [...el.ordersList.querySelectorAll(".order-row")]
    .map(resolveRow)
    .filter(Boolean);
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
