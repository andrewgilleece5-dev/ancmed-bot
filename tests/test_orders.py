"""Every leaf of the friendly order tree must be an order the engine allows."""

import os
import sys

import pytest
from diplomacy import Game

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from server.bot import DumbBot  # noqa: E402
from server.orders import order_tree  # noqa: E402


def _leaf_orders(node):
    for action in node["actions"]:
        if action.get("order"):
            yield action["order"]
        for entry in action.get("targets", []) + action.get("moves", []):
            yield entry["order"]


@pytest.mark.parametrize("map_name", ["ancmed", "standard", "modern"])
def test_order_tree_leaves_are_legal(map_name):
    game = Game(map_name=map_name)
    names = {c: f.title() for f, c in game.map.loc_name.items()}
    bot = DumbBot(seed=11)
    seen = set()

    for _ in range(80):
        if game.is_game_done:
            break
        seen.add(game.phase_type)
        possible = game.get_all_possible_orders()
        legal = set()
        for opts in possible.values():
            legal.update(opts)

        for power in game.powers:
            for loc in game.get_orderable_locations(power):
                node = order_tree(loc, possible.get(loc, []), game.phase_type, names.get)
                assert node["actions"], (map_name, power, loc, game.get_current_phase())
                for order in _leaf_orders(node):
                    assert order in legal, (map_name, loc, order)
            game.set_orders(power, bot.get_orders(game, power))
        game.process()

    assert {"M", "A"} <= seen


def test_retreat_phase_has_disband_and_retreat_options():
    game = Game(map_name="standard")
    game.set_orders("GERMANY", ["A BER - PRU", "A MUN - SIL"])
    game.set_orders("RUSSIA", ["A WAR H", "A MOS - LVN"])
    game.process()  # F1901M
    game.set_orders("GERMANY", ["A PRU - WAR", "A SIL S A PRU - WAR"])
    game.set_orders("RUSSIA", ["A WAR H"])
    game.process()
    assert game.phase_type == "R"
    possible = game.get_all_possible_orders()
    russia_locs = game.get_orderable_locations("RUSSIA")
    assert russia_locs
    node = order_tree(russia_locs[0], possible[russia_locs[0]], "R", None)
    types = {a["type"] for a in node["actions"]}
    assert "disband" in types and "retreat" in types
    legal = {o for opts in possible.values() for o in opts}
    for order in _leaf_orders(node):
        assert order in legal
