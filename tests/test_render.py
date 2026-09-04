"""Board post-processing: alias fixes, home-territory tint, historical phases."""

import os
import re
import sys

from diplomacy import Game

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from server.bot import DumbBot  # noqa: E402
from server.render import render_board  # noqa: E402


def _class_of(svg, svg_id):
    m = re.search(r'<(?:polygon|path|g)\b[^>]*\bid="_%s"[^>]*>' % svg_id, svg)
    assert m, "no element _%s" % svg_id
    c = re.search(r'class="([^"]+)"', m.group(0))
    return c.group(1) if c else None


def test_modern_aliased_supply_centres_are_coloured():
    svg = render_board(Game(map_name="modern"), "modern")
    assert _class_of(svg, "svl") == "spain"     # Seville
    assert _class_of(svg, "lpl") == "britain"   # Liverpool


def test_modern_home_territory_is_tinted_from_turn_one():
    svg = render_board(Game(map_name="modern"), "modern")
    for svg_id, power in [("sax", "germany"), ("nav", "spain"), ("ana", "turkey"),
                          ("ruh", "germany"), ("sib", "russia")]:
        assert _class_of(svg, svg_id) == power, svg_id


def test_ancmed_and_standard_render_unchanged_size():
    for name in ("ancmed", "standard"):
        svg = render_board(Game(map_name=name), name)
        assert svg.startswith("<?xml") and len(svg) > 10000


def test_historical_phase_renders_with_order_arrows():
    game = Game(map_name="ancmed")
    bot = DumbBot(seed=4)
    for _ in range(3):
        for power in game.powers:
            game.set_orders(power, bot.get_orders(game, power))
        game.process()
    history = game.get_phase_history()
    svg = render_board(game, "ancmed", phase=history[0])
    assert svg
    # the renderer draws orders as var-width / support / shadow strokes
    assert re.search(r'class="(?:varwidthorder|supportorder|shadowdash)"', svg)
