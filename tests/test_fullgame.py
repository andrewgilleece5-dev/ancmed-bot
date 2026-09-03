"""End-to-end: a full DumbBot-vs-DumbBot game runs without crashing and,
on the competitive maps, actually resolves to a winner or a draw."""

import os
import sys

import pytest
from diplomacy import Game

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from server.bot import DumbBot  # noqa: E402


@pytest.mark.parametrize("map_name", ["ancmed", "standard"])
def test_full_game_resolves(map_name):
    game = Game(map_name=map_name)
    bot = DumbBot(seed=123)

    phases = 0
    while not game.is_game_done and phases < 600:
        for power in game.powers:
            game.set_orders(power, bot.get_orders(game, power))
        game.process()
        phases += 1

    assert game.is_game_done, f"{map_name} did not finish in {phases} phases"
    winners = list(getattr(game, "outcome", []) or [])[1:]
    assert winners, "game ended with no winner/draw recorded"

    total = sum(len(c) for c in game.get_state()["centers"].values())
    assert total > 0


def test_advance_helper_keeps_human_in_sync():
    from server.app import _advance

    game = Game(map_name="ancmed")
    meta = {"human_power": "ROME", "bot": "dumbbot"}

    # submit a couple of legal human orders, then let the helper run the bots
    possible = game.get_all_possible_orders()
    human_orders = [possible[loc][0] for loc in game.get_orderable_locations("ROME")]
    _advance(game, meta, human_orders)

    assert game.get_current_phase() != "S0001M"
    # helper must always leave the game on a phase the human can act on, or done
    assert game.is_game_done or game.get_orderable_locations("ROME") or "ROME" not in [
        pw for pw, c in game.get_state()["centers"].items() if c
    ]
