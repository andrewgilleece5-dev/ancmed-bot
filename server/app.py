"""HTTP API + static hosting for playing Diplomacy against bots.

Routes
------
GET  /api/maps                 list playable maps and their powers
POST /api/games                {map_name, power, difficulty} -> new game + state
GET  /api/games/{id}           current state (svg + friendly order tree)
POST /api/games/{id}/orders    {orders:[...]} -> submit, run the bots, advance
GET  /api/games/{id}/phase/{i} a past phase re-rendered with its move arrows
GET  /api/games/{id}/svg       raw rendered board svg
/                              single-page UI from ./web
"""

import os
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from diplomacy import Game

from .bot import make_bot
from .orders import order_tree, parse
from .render import render_board
from .store import GameStore

WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "web"))
SOURCE_URL = os.environ.get("ANCMED_SOURCE_URL", "https://github.com/diplomacy/diplomacy")

PLAYABLE_MAPS = [
    ("ancmed", "Ancient Mediterranean"),
    ("standard", "Classic (Europe)"),
    ("pure", "Pure (topology only)"),
    ("modern", "Modern"),
]
DIFFICULTIES = ["easy", "medium", "hard"]

app = FastAPI(title="Diplomacy vs. Bots")
store = GameStore()

_POWERS_CACHE = {}
_NAMES_CACHE = {}
_PHASE_SVG_CACHE = {}  # (game_id, index) -> svg


def powers_for(map_name):
    if map_name not in _POWERS_CACHE:
        _POWERS_CACHE[map_name] = sorted(Game(map_name=map_name).powers)
    return _POWERS_CACHE[map_name]


def province_names(map_name):
    """CODE -> 'Full Name' for a map (inverted `map.loc_name`)."""
    if map_name not in _NAMES_CACHE:
        loc_name = Game(map_name=map_name).map.loc_name
        _NAMES_CACHE[map_name] = {code: full.title() for full, code in loc_name.items()}
    return _NAMES_CACHE[map_name]


class NewGameRequest(BaseModel):
    map_name: str = "ancmed"
    power: str
    difficulty: str = "medium"


class OrdersRequest(BaseModel):
    orders: List[str] = []


# --------------------------------------------------------------------- state
def _results_payload(phase_data):
    return {
        "phase": phase_data.name,
        "orders": {pw: list(olist) for pw, olist in (phase_data.orders or {}).items()},
        "results": {
            unit: [str(tag) for tag in tags if str(tag)]
            for unit, tags in (phase_data.results or {}).items()
            if any(str(tag) for tag in tags)
        },
    }


def _phase_label(phase):
    if phase in ("COMPLETED", "FORMING"):
        return phase.title()
    season = {"S": "Spring", "F": "Fall", "W": "Winter"}.get(phase[0], phase[0])
    kind = {"M": "Movement", "R": "Retreats", "A": "Adjustments"}.get(phase[-1], "")
    year = phase[1:-1].lstrip("0") or phase[1:-1]
    return "%s %s · %s" % (season, year, kind)


def _state(game_id):
    game, meta = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="no such game")

    map_name = meta["map_name"]
    human = meta["human_power"]
    done = game.is_game_done
    names = province_names(map_name)

    orderable = {}
    builds_allowed = None
    if not done and human in game.powers:
        possible = game.get_all_possible_orders()
        for loc in game.get_orderable_locations(human):
            opts = possible.get(loc, [])
            if opts:
                orderable[loc] = order_tree(loc, opts, game.phase_type, names.get)
        if game.phase_type == "A":
            power = game.get_power(human)
            builds_allowed = max(0, len(power.centers) - len(power.units))

    centers = game.get_state()["centers"]
    history = [
        {"index": i, "name": ph.name, "label": _phase_label(ph.name)}
        for i, ph in enumerate(game.get_phase_history())
    ]

    return {
        "game_id": game_id,
        "map_name": map_name,
        "your_power": human,
        "difficulty": meta.get("bot", "medium"),
        "phase": game.get_current_phase(),
        "phase_type": game.phase_type,
        "phase_long": _phase_label(game.get_current_phase()),
        "is_done": done,
        "outcome": list(getattr(game, "outcome", []) or []),
        "win_centers": getattr(game, "win", None),
        "powers": sorted(game.powers),
        "sc_counts": {pw: len(v) for pw, v in centers.items()},
        "eliminated": [pw for pw in game.powers if not centers.get(pw)],
        "orderable": orderable,
        "builds_allowed": builds_allowed,
        "province_names": names,
        "history": history,
        "last_phase": _results_payload(game.get_phase_history()[-1])
        if game.get_phase_history()
        else None,
        "svg": render_board(game, map_name),
        "source_url": SOURCE_URL,
    }


# ------------------------------------------------------------------- advance
def _advance(game, meta, human_orders):
    human = meta["human_power"]
    bot = make_bot(meta.get("bot", "medium"))
    if game.is_game_done:
        return

    allowed = set()
    for opts in game.get_all_possible_orders().values():
        allowed.update(opts)
    clean = [o for o in (human_orders or []) if o in allowed]

    # never submit more builds than are allowed - the engine waives the rest
    if game.phase_type == "A" and human in game.powers:
        power = game.get_power(human)
        cap = len(power.centers) - len(power.units)
        if cap > 0:
            builds = [o for o in clean if parse(o)["action"] == "build"]
            if len(builds) > cap:
                drop = set(builds[cap:])
                clean = [o for o in clean if o not in drop]

    if human in game.powers:
        game.set_orders(human, clean)
    for pw in game.powers:
        if pw == human:
            continue
        try:
            game.set_orders(pw, bot.get_orders(game, pw))
        except Exception:  # pragma: no cover
            pass
    game.process()

    # Auto-play following phases the human can't act on (bot-only retreats,
    # adjustment phases the human can't build in, the whole game once eliminated).
    def human_alive():
        return bool(game.get_state()["centers"].get(human))

    for _ in range(2000):
        if game.is_game_done or game.get_orderable_locations(human):
            break
        if human_alive() and game.phase_type == "M":
            break
        for pw in game.powers:
            try:
                game.set_orders(pw, bot.get_orders(game, pw))
            except Exception:  # pragma: no cover
                pass
        game.process()


# --------------------------------------------------------------------- API
@app.get("/api/maps")
def list_maps():
    out = []
    for name, label in PLAYABLE_MAPS:
        try:
            out.append({"name": name, "label": label, "powers": powers_for(name)})
        except Exception:  # pragma: no cover
            continue
    return {"maps": out, "difficulties": DIFFICULTIES}


@app.post("/api/games")
def create_game(req: NewGameRequest):
    if req.map_name not in {name for name, _ in PLAYABLE_MAPS}:
        raise HTTPException(status_code=400, detail="unknown map")
    if req.power.upper() not in powers_for(req.map_name):
        raise HTTPException(status_code=400, detail="unknown power for this map")
    difficulty = req.difficulty if req.difficulty in DIFFICULTIES else "medium"
    game_id = store.create(req.map_name, req.power.upper(), bot=difficulty)
    return _state(game_id)


@app.get("/api/games/{game_id}")
def read_game(game_id: str):
    return _state(game_id)


@app.post("/api/games/{game_id}/orders")
def submit_orders(game_id: str, req: OrdersRequest):
    game, meta = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="no such game")
    with store.lock(game_id):
        _advance(game, meta, req.orders)
        store.persist(game_id)
    _PHASE_SVG_CACHE.clear()
    return _state(game_id)


@app.get("/api/games/{game_id}/phase/{index}")
def read_phase(game_id: str, index: int):
    game, meta = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="no such game")
    history = game.get_phase_history()
    if index < 0 or index >= len(history):
        raise HTTPException(status_code=404, detail="no such phase")
    phase_data = history[index]
    key = (game_id, index)
    if key not in _PHASE_SVG_CACHE:
        if len(_PHASE_SVG_CACHE) > 400:
            _PHASE_SVG_CACHE.clear()
        _PHASE_SVG_CACHE[key] = render_board(game, meta["map_name"], phase=phase_data)
    payload = _results_payload(phase_data)
    payload["index"] = index
    payload["label"] = _phase_label(phase_data.name)
    payload["svg"] = _PHASE_SVG_CACHE[key]
    return payload


@app.get("/api/games/{game_id}/svg")
def game_svg(game_id: str):
    game, meta = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="no such game")
    return Response(
        content=render_board(game, meta["map_name"]), media_type="image/svg+xml"
    )


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
