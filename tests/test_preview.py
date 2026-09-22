"""The /preview endpoint backs the click-to-order map: it must render exactly
the orders it's given, as arrows, without ever mutating or persisting the
stored game (the real submit endpoint owns that)."""

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

import server.app as app_module  # noqa: E402


class _Req:
    def __init__(self, orders):
        self.orders = orders


def _arrow_count(svg):
    return len(re.findall(r'class="(?:varwidthorder|supportorder|convoyorder|shadowdash)"', svg))


def test_preview_draws_only_the_given_orders_and_does_not_mutate_the_game():
    gid = app_module.store.create("ancmed", "ROME", bot="medium")
    game, meta = app_module.store.get(gid)
    before_phase = game.get_current_phase()

    empty = app_module.preview_orders(gid, _Req([]))
    assert _arrow_count(empty["svg"]) == 0

    one = app_module.preview_orders(gid, _Req(["A ROM - APU"]))
    assert _arrow_count(one["svg"]) == 1

    two = app_module.preview_orders(gid, _Req(["A ROM - APU", "A RAV - ROM"]))
    assert _arrow_count(two["svg"]) == 2

    # the stored game itself must be untouched by any of the previews above
    game_after, _ = app_module.store.get(gid)
    assert game_after.get_current_phase() == before_phase
    assert game_after.get_orders("ROME") == []


def test_preview_ignores_illegal_orders():
    gid = app_module.store.create("ancmed", "ROME", bot="medium")
    result = app_module.preview_orders(gid, _Req(["A ROM - NOWHERE", "NOT AN ORDER"]))
    assert _arrow_count(result["svg"]) == 0


def test_preview_unknown_game_404s():
    from fastapi import HTTPException
    import pytest

    with pytest.raises(HTTPException):
        app_module.preview_orders("no-such-game", _Req([]))
