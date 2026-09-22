"""The bot must only ever emit orders the engine considers legal."""

import os
import sys

import pytest
from diplomacy import Game

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from server.bot import DumbBot  # noqa: E402


@pytest.mark.parametrize(
    "map_name,level",
    [
        ("ancmed", "easy"), ("ancmed", "medium"), ("ancmed", "hard"),
        ("standard", "medium"), ("standard", "hard"), ("pure", "medium"),
    ],
)
def test_every_bot_order_is_legal(map_name, level):
    game = Game(map_name=map_name)
    bot = DumbBot(seed=7, level=level)
    seen_phase_types = set()

    for _ in range(60 if level == "hard" else 80):
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


def test_make_bot_maps_legacy_name():
    from server.bot import make_bot

    assert make_bot("dumbbot").level == "medium"
    assert make_bot("hard").level == "hard"
    assert make_bot("nonsense").level == "medium"


def _navarre_threatens_portugal():
    """France has a fleet that can take Spain's Portugal (coastal) but never
    Madrid (inland - fleets can't go there). Regression for a bug where the
    Portugal garrison abandoned its post (often for a doomed lone attack on
    the French fleet, sometimes dressed up as "defending" an inland capital a
    fleet could never actually reach) because the shared, diffused value field
    - not a real, reachability-checked threat - made leaving look attractive."""
    game = Game(map_name="modern")
    game.clear_units()
    game.set_units("FRANCE", ["F NAV"])
    game.set_units("SPAIN", ["A POR", "A MAD"])
    game.clear_centers()
    game.set_centers("FRANCE", ["PAR", "MAR", "BOR", "LYO"])
    game.set_centers("SPAIN", ["MAD", "BAR", "SVE", "POR"])
    return game


def test_hard_bot_holds_a_directly_threatened_centre():
    game = _navarre_threatens_portugal()
    for seed in range(15):
        bot = DumbBot(seed=seed, level="hard")
        orders = bot.get_orders(game, "SPAIN")
        assert "A POR H" in orders, orders


def test_medium_bot_mostly_holds_a_directly_threatened_centre():
    game = _navarre_threatens_portugal()
    holds = sum(
        1 for seed in range(20)
        if "A POR H" in DumbBot(seed=seed, level="medium").get_orders(game, "SPAIN")
    )
    assert holds >= 14  # clearly the modal choice, not a coin flip
