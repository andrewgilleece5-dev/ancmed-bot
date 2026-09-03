"""HTTP API + static hosting for playing Diplomacy against bots.

Routes
------
GET  /api/maps               list playable maps and their powers
POST /api/games              {map_name, power} -> new game, returns state
GET  /api/games/{id}         current state (svg + your orderable locations)
POST /api/games/{id}/orders  {orders:[...]} -> submit, run the bots, advance
GET  /api/games/{id}/svg     raw rendered board svg
/                            single-page UI from ./web
"""

import os
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from diplomacy import Game

from .bot import make_bot
from .store import GameStore

WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "web"))
SOURCE_URL = os.environ.get(
    "ANCMED_SOURCE_URL", "https://github.com/diplomacy/diplomacy"
)

PLAYABLE_MAPS = [
    ("ancmed", "Ancient Mediterranean"),
    ("standard", "Classic (Europe)"),
    ("pure", "Pure (topology only)"),
    ("modern", "Modern"),
]

app = FastAPI(title="Diplomacy vs. Bots")
store = GameStore()

_POWERS_CACHE = {}


def powers_for(map_name):
    if map_name not in _POWERS_CACHE:
        _POWERS_CACHE[map_name] = sorted(Game(map_name=map_name).powers)
    return _POWERS_CACHE[map_name]


class NewGameRequest(BaseModel):
    map_name: str = "ancmed"
    power: str


class OrdersRequest(BaseModel):
    orders: List[str] = []


# --------------------------------------------------------------------- state
def _phase_results(game):
    history = game.get_phase_history()
    if not history:
        return None
    last = history[-1]
    return {
        "phase": last.name,
        "orders": {pw: list(olist) for pw, olist in (last.orders or {}).items()},
        "results": {
            unit: [str(tag) for tag in tags]
            for unit, tags in (last.results or {}).items()
            if tags
        },
    }


def _state(game_id):
    game, meta = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="no such game")

    human = meta["human_power"]
    done = game.is_game_done
    orderable = {}
    if not done and human in game.powers:
        possible = game.get_all_possible_orders()
        for loc in game.get_orderable_locations(human):
            opts = sorted(possible.get(loc, []))
            if opts:
                orderable[loc] = opts

    centers = game.get_state()["centers"]
    sc_counts = {pw: len(v) for pw, v in centers.items()}

    return {
        "game_id": game_id,
        "map_name": meta["map_name"],
        "your_power": human,
        "phase": game.get_current_phase(),
        "phase_type": game.phase_type,
        "phase_long": _phase_label(game),
        "is_done": done,
        "outcome": list(getattr(game, "outcome", []) or []),
        "win_centers": getattr(game, "win", None),
        "powers": sorted(game.powers),
        "sc_counts": sc_counts,
        "eliminated": [pw for pw in game.powers if not centers.get(pw)],
        "orderable": orderable,
        "last_phase": _phase_results(game),
        "svg": game.render(incl_orders=True, incl_abbrev=False),
        "source_url": SOURCE_URL,
    }


def _phase_label(game):
    phase = game.get_current_phase()
    if phase in ("COMPLETED", "FORMING"):
        return phase.title()
    season = {"S": "Spring", "F": "Fall", "W": "Winter"}.get(phase[0], phase[0])
    kind = {"M": "Movement", "R": "Retreats", "A": "Adjustments"}.get(phase[-1], "")
    year = phase[1:-1].lstrip("0") or phase[1:-1]
    return "%s %s - %s" % (season, year, kind)


# ------------------------------------------------------------------- advance
def _advance(game, meta, human_orders):
    human = meta["human_power"]
    bot = make_bot(meta.get("bot", "dumbbot"))
    if game.is_game_done:
        return

    allowed = set()
    for opts in game.get_all_possible_orders().values():
        allowed.update(opts)
    clean = [o for o in (human_orders or []) if o in allowed]

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

    # Auto-play any following phases the human has nothing to decide on:
    # bot-only retreats, adjustment phases the human can't build in, and - once
    # the human has been eliminated - the entire rest of the game.
    def human_still_playing():
        return bool(game.get_state()["centers"].get(human))

    for _ in range(2000):
        if game.is_game_done:
            break
        if game.get_orderable_locations(human):
            break
        if human_still_playing() and game.phase_type == "M":
            # human is alive but has no units to move (all dislodged/awaiting
            # builds handled above) - nothing sensible left to auto-run
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
        except Exception:  # pragma: no cover - skip a map that won't load
            continue
    return out


@app.post("/api/games")
def create_game(req: NewGameRequest):
    valid = {name for name, _ in PLAYABLE_MAPS}
    if req.map_name not in valid:
        raise HTTPException(status_code=400, detail="unknown map")
    if req.power.upper() not in powers_for(req.map_name):
        raise HTTPException(status_code=400, detail="unknown power for this map")
    game_id = store.create(req.map_name, req.power.upper())
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
    return _state(game_id)


@app.get("/api/games/{game_id}/svg")
def game_svg(game_id: str):
    game, _ = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="no such game")
    return Response(content=game.render(incl_orders=True), media_type="image/svg+xml")


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
