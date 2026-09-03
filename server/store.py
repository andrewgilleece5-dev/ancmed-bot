"""In-memory game store with best-effort JSON persistence to disk.

One :class:`diplomacy.Game` lives per game id. Games are also written to
``$ANCMED_DATA_DIR`` (default ``./data``) after every change so a process
restart - or a browser refresh days later - can resume. On hosts with only
ephemeral disk (e.g. Render's free tier) persistence is a bonus, not a
guarantee; the in-memory copy is the source of truth while the process lives.
"""

import json
import os
import threading
import time
import uuid

from diplomacy import Game
from diplomacy.utils.export import from_saved_game_format, to_saved_game_format

_DEFAULT_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")
DATA_DIR = os.path.abspath(os.environ.get("ANCMED_DATA_DIR", _DEFAULT_DIR))


class GameStore:
    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = os.path.abspath(data_dir)
        os.makedirs(self.data_dir, exist_ok=True)
        self._games = {}
        self._meta = {}
        self._locks = {}
        self._guard = threading.Lock()

    # ------------------------------------------------------------------ paths
    def _path(self, game_id):
        return os.path.join(self.data_dir, "%s.json" % game_id)

    # ----------------------------------------------------------------- create
    def create(self, map_name, human_power, bot="dumbbot"):
        game_id = uuid.uuid4().hex[:12]
        game = Game(map_name=map_name)
        meta = {
            "human_power": human_power.upper(),
            "map_name": map_name,
            "bot": bot,
            "created": time.time(),
        }
        with self._guard:
            self._games[game_id] = game
            self._meta[game_id] = meta
            self._locks[game_id] = threading.Lock()
        self.persist(game_id)
        return game_id

    # -------------------------------------------------------------------- get
    def lock(self, game_id):
        with self._guard:
            return self._locks.setdefault(game_id, threading.Lock())

    def get(self, game_id):
        with self._guard:
            if game_id in self._games:
                return self._games[game_id], self._meta[game_id]

        path = self._path(game_id)
        if not os.path.exists(path):
            return None, None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                blob = json.load(handle)
            game = from_saved_game_format(blob["saved_game"])
            meta = blob["meta"]
        except (OSError, ValueError, KeyError):
            return None, None

        with self._guard:
            self._games.setdefault(game_id, game)
            self._meta.setdefault(game_id, meta)
            self._locks.setdefault(game_id, threading.Lock())
            return self._games[game_id], self._meta[game_id]

    # --------------------------------------------------------------- persist
    def persist(self, game_id):
        with self._guard:
            game = self._games.get(game_id)
            meta = self._meta.get(game_id)
        if game is None:
            return
        blob = {"meta": meta, "saved_game": to_saved_game_format(game)}
        tmp = self._path(game_id) + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(blob, handle)
            os.replace(tmp, self._path(game_id))
        except OSError:
            pass  # ephemeral disk / read-only fs - keep going with the in-memory copy
