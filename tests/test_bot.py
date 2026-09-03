"""The bot must only ever emit orders the engine considers legal."""

import os
import sys

import pytest
from diplomacy import Game

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from server.bot import DumbBot  # noqa: E402


@pytest.mark.parametrize("map_name", ["ancmed", "standard", "pure"])
def test_every_bot_order_is_legal(map_name):
    game = Game(map_name=map_name)
    bot = DumbBot(seed=7)
    seen_phase_types = set()

    for _ in range(80):
        if game.is_game_done:
            break
        seen_phase_types.add(game.phase_type)
        possible = game.get_all_possible_orders()
        legal = set()
        for opts in possible.values():
            legal.update(opts)

        for power in game.powers:
            orders = bot.get_orders(game, power)
            assert isinstance(orders, list)
            for order in orders:
                assert order in legal, (map_name, power, game.get_current_phase(), order)
            game.set_orders(power, orders)
        game.process()

    # a full run should exercise movement, retreats and adjustments
    assert "M" in seen_phase_types


def test_bot_handles_adjustment_builds_and_disbands():
    game = Game(map_name="ancmed")
    bot = DumbBot(seed=3)
    hit_adjustment = False
    for _ in range(60):
        if game.is_game_done:
            break
        if game.phase_type == "A":
            hit_adjustment = True
            for power in game.powers:
                build = game.get_state()["builds"][power]
                orders = bot.get_orders(game, power)
                if build["count"] > 0:
                    assert len(orders) <= build["count"]
                game.set_orders(power, orders)
        else:
            for power in game.powers:
                game.set_orders(power, bot.get_orders(game, power))
        game.process()
    assert hit_adjustment
