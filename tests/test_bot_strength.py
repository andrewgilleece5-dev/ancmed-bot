"""Coarse strength / aggression checks for the difficulty levels.

These play whole games, so they are slow and a little stochastic; the assertions
have wide margins and average several seeds. They guard against regressions like
"every game is a passive 5-way draw" or "hard is weaker than medium".
"""

import os
import statistics
import sys
import time

import pytest
from diplomacy import Game

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from server.bot import DumbBot  # noqa: E402


def _play(map_name, levels, seed, cap=260):
    game = Game(map_name=map_name)
    powers = sorted(game.powers)
    bots = {pw: DumbBot(seed=seed + i, level=levels[pw]) for i, pw in enumerate(powers)}
    n = 0
    while not game.is_game_done and n < cap:
        for pw in game.powers:
            game.set_orders(pw, bots[pw].get_orders(game, pw))
        game.process()
        n += 1
    return {pw: len(c) for pw, c in game.get_state()["centers"].items()}, game.is_game_done


@pytest.mark.parametrize("level", ["medium", "hard"])
@pytest.mark.parametrize("map_name", ["ancmed", "standard"])
def test_games_are_decisive(map_name, level):
    """A field of same-level bots should actually resolve - a clear leader
    emerges, not everyone stuck on their starting centres (the pre-v3 bug)."""
    tops = []
    powers = sorted(Game(map_name=map_name).powers)
    for i in range(3):
        sc, _ = _play(map_name, {pw: level for pw in powers}, seed=700 + i * 11)
        tops.append(max(sc.values()))
    assert statistics.mean(tops) >= 10, (level, tops)


@pytest.mark.parametrize("field", ["medium", "hard"])
def test_easy_bot_is_outclassed(field):
    """A lone easy bot dropped into a field of medium/hard bots should end up
    well below the pack - easy is deliberately sloppy and doesn't coordinate."""
    powers = sorted(Game(map_name="ancmed").powers)
    easy_sc, field_sc = [], []
    for i in range(3):
        ep = powers[i]
        levels = {pw: ("easy" if pw == ep else field) for pw in powers}
        sc, _ = _play("ancmed", levels, seed=200 + i * 7)
        easy_sc.append(sc[ep])
        field_sc.append(statistics.mean(sc[pw] for pw in powers if pw != ep))
    assert statistics.mean(easy_sc) + 1.5 < statistics.mean(field_sc), (easy_sc, field_sc)


def test_turn_time_within_budget():
    game = Game(map_name="modern")
    bots = {pw: DumbBot(seed=1, level="hard") for pw in game.powers}
    start = time.time()
    for _ in range(6):
        for pw in game.powers:
            game.set_orders(pw, bots[pw].get_orders(game, pw))
        game.process()
    per_turn = (time.time() - start) / 6
    assert per_turn < 2.0, per_turn
