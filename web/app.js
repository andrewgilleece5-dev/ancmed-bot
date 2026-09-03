"use strict";

const $ = (sel) => document.querySelector(sel);
const KEY = "ancmed_game_id";

const els = {
  setup: $("#setup"),
  setupError: $("#setup-error"),
  game: $("#game"),
  status: $("#status"),
  newGameBtn: $("#new-game-btn"),
  mapSelect: $("#map-select"),
  powerSelect: $("#power-select"),
  mapNote: $("#map-note"),
  startBtn: $("#start-btn"),
  mapHolder: $("#map-holder"),
  banner: $("#banner"),
  scTable: $("#sc-table"),
  winNote: $("#win-note"),
  ordersCard: $("#orders-card"),
  ordersTitle: $("#orders-title"),
  ordersList: $("#orders-list"),
  submitBtn: $("#submit-btn"),
  ordersHint: $("#orders-hint"),
  resultsCard: $("#results-card"),
  resultsBody: $("#results-body"),
  overlay: $("#overlay"),
  sourceLink: $("#source-link"),
};

let MAPS = [];

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

/* ---------------------------------------------------------------- setup --- */
async function initSetup() {
  MAPS = await api("/api/maps");
  els.mapSelect.innerHTML = MAPS.map(
    (m) => `<option value="${m.name}">${m.label}</option>`
  ).join("");
  els.mapSelect.onchange = fillPowers;
  fillPowers();
}

function fillPowers() {
  const map = MAPS.find((m) => m.name === els.mapSelect.value);
  els.powerSelect.innerHTML = map.powers
    .map((p) => `<option value="${p}">${title(p)}</option>`)
    .join("");
  els.mapNote.textContent = `${map.powers.length} powers. You play one, bots play the rest.`;
}

els.startBtn.onclick = async () => {
  els.startBtn.disabled = true;
  els.setupError.hidden = true;
  try {
    const state = await api("/api/games", {
      method: "POST",
      body: JSON.stringify({
        map_name: els.mapSelect.value,
        power: els.powerSelect.value,
      }),
    });
    localStorage.setItem(KEY, state.game_id);
    render(state);
  } catch (err) {
    els.setupError.textContent = err.message;
    els.setupError.hidden = false;
  } finally {
    els.startBtn.disabled = false;
  }
};

els.newGameBtn.onclick = () => {
  localStorage.removeItem(KEY);
  showSetup();
};

function showSetup() {
  els.game.hidden = true;
  els.setup.hidden = false;
  els.newGameBtn.hidden = true;
  els.status.textContent = "";
}

/* ----------------------------------------------------------------- game --- */
function powerColors(svgText) {
  const colors = {};
  const re = /\.([a-z]+)\s*\{[^}]*fill\s*:\s*([^;]+);/g;
  let m;
  while ((m = re.exec(svgText))) {
    if (!m[1].startsWith("unit") && !colors[m[1].toUpperCase()]) {
      colors[m[1].toUpperCase()] = m[2].trim();
    }
  }
  return colors;
}

function render(state) {
  els.setup.hidden = true;
  els.game.hidden = false;
  els.newGameBtn.hidden = false;
  els.sourceLink.innerHTML = "";

  els.status.textContent = `${title(state.map_name)} — you are ${title(
    state.your_power
  )} — ${state.phase_long}`;

  els.mapHolder.innerHTML = state.svg;
  const colors = powerColors(state.svg);

  // supply centres
  const rows = state.powers
    .map((pw) => {
      const n = state.sc_counts[pw] || 0;
      const out = state.eliminated.includes(pw);
      const cls = [pw === state.your_power ? "you" : "", out ? "out" : ""]
        .join(" ")
        .trim();
      const sw = colors[pw]
        ? `<span class="swatch" style="background:${colors[pw]}"></span>`
        : "";
      return `<tr class="${cls}"><td>${sw}${title(pw)}</td><td class="n">${n}</td></tr>`;
    })
    .join("");
  els.scTable.innerHTML = rows;
  els.winNote.textContent = state.win_centers
    ? `${state.win_centers} centres to win.`
    : "";

  // banner / end state
  if (state.is_done) {
    els.banner.hidden = false;
    els.banner.textContent = endText(state);
    els.ordersCard.hidden = true;
  } else {
    els.banner.hidden = true;
    els.ordersCard.hidden = false;
    renderOrders(state);
  }

  renderResults(state);
}

function renderOrders(state) {
  const locs = Object.keys(state.orderable).sort();
  els.ordersTitle.textContent =
    { M: "Orders", R: "Retreats", A: "Builds / disbands" }[state.phase_type] ||
    "Orders";

  if (!locs.length) {
    els.ordersList.innerHTML = `<p class="note">Nothing for you to order this phase.</p>`;
    els.ordersHint.textContent = "Submit to let the bots move.";
  } else {
    els.ordersList.innerHTML = locs
      .map((loc) => {
        const opts = state.orderable[loc];
        const def = defaultOrder(opts, state.phase_type);
        return `<div class="order-row"><label>${loc}</label>
          <select data-loc="${loc}">
            ${opts
              .map(
                (o) =>
                  `<option value="${o}"${o === def ? " selected" : ""}>${o}</option>`
              )
              .join("")}
            ${state.phase_type === "A" ? `<option value="">(no order)</option>` : ""}
          </select></div>`;
      })
      .join("");
    els.ordersHint.textContent =
      state.phase_type === "A"
        ? "Pick builds/disbands. Leaving a slot on “(no order)” waives it."
        : "Defaults to hold. Change what you like, then submit.";
  }

  els.submitBtn.onclick = () => submit(state.game_id);
}

function defaultOrder(opts, phaseType) {
  if (phaseType === "M") {
    const hold = opts.find((o) => / H$/.test(o));
    if (hold) return hold;
  }
  if (phaseType === "R") {
    const disband = opts.find((o) => / D$/.test(o));
    if (disband) return disband;
  }
  return opts[0];
}

async function submit(gameId) {
  els.overlay.hidden = false;
  const orders = [...els.ordersList.querySelectorAll("select")]
    .map((s) => s.value)
    .filter(Boolean);
  try {
    const state = await api(`/api/games/${gameId}/orders`, {
      method: "POST",
      body: JSON.stringify({ orders }),
    });
    render(state);
  } catch (err) {
    alert(err.message);
  } finally {
    els.overlay.hidden = true;
  }
}

function renderResults(state) {
  const last = state.last_phase;
  if (!last) {
    els.resultsCard.hidden = true;
    return;
  }
  els.resultsCard.hidden = false;
  els.resultsCard.querySelector("summary").textContent = `${last.phase} results`;
  const blocks = Object.keys(last.orders)
    .sort()
    .map((pw) => {
      const lines = last.orders[pw]
        .map((o) => {
          const unit = o.split(" ").slice(0, 2).join(" ");
          const tags = last.results[unit] || [];
          const failed = tags.some((t) =>
            /bounce|void|no convoy|disband|dislodged|cut/.test(t)
          );
          const suffix = tags.length ? ` (${tags.join(", ")})` : "";
          return `<span class="o${failed ? " fail" : ""}">${o}${suffix}</span>`;
        })
        .join("");
      return `<div class="pw">${title(pw)}</div>${lines || '<span class="o">—</span>'}`;
    })
    .join("");
  els.resultsBody.innerHTML = blocks;
}

function endText(state) {
  const o = state.outcome || [];
  const winners = o.slice(1);
  if (winners.length === 1) return `Game over — ${title(winners[0])} wins.`;
  if (winners.length > 1)
    return `Game over — draw between ${winners.map(title).join(", ")}.`;
  return "Game over.";
}

/* --------------------------------------------------------------- helpers --- */
function title(s) {
  return s ? s[0].toUpperCase() + s.slice(1).toLowerCase() : s;
}

/* ----------------------------------------------------------------- boot --- */
(async function boot() {
  await initSetup();
  const saved = localStorage.getItem(KEY);
  if (saved) {
    try {
      render(await api(`/api/games/${saved}`));
      return;
    } catch (_) {
      localStorage.removeItem(KEY);
    }
  }
  showSetup();
})();
