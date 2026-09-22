"""Documents a DATC rule a user reported as "missing": a support order is cut
by *any* attack on the supporting unit - even one that ultimately fails - and
a third unit merely supporting the supporter to *hold* does not restore it.
This is standard Diplomacy adjudication (not a webDiplomacy-specific rule),
and the `diplomacy` engine (a DATC-compliant adjudicator - see its own
README) already gets it right; there is nothing in this app to fix. This test
exists so the scenario is verified against the real adjudicator, and so a
future report of the same shape can be checked here first.

Scenario (Modern map): France attacks Tunisia from Western Med, supported by
its fleet in Algeria. Egypt counter-attacks Algeria from Libya, supported by
its army in Tunisia. Both supports get cut (each attacked from outside the
province their support targets) and both moves bounce. Adding a THIRD unit -
Egypt's fleet in the Maltese Sea, supporting Tunisia to *hold* - does not
change the outcome: Tunisia's support of the Libya-Algeria move was for a
*support* order, not a hold, and support-hold only ever backs a unit's actual
non-move order; it cannot "un-cut" a support that a different attack already
cut. Egypt's move into Algeria still needs its own, uncut support to succeed,
and doesn't have it.
"""

import os
import sys

from diplomacy import Game

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))


def _play(escort_tunisia_with_maltese_sea):
    game = Game(map_name="modern")
    game.clear_units()
    game.set_units("FRANCE", ["F WME", "F ALG"])
    game.set_units("EGYPT", ["A LIB", "A TUN", "F MAL"])
    game.set_orders("FRANCE", ["F WME - TUN", "F ALG S F WME - TUN"])
    egypt_orders = ["A LIB - ALG", "A TUN S A LIB - ALG"]
    egypt_orders.append("F MAL S A TUN" if escort_tunisia_with_maltese_sea else "F MAL H")
    game.set_orders("EGYPT", egypt_orders)
    game.process()
    return game.get_phase_history()[-1].results, game.get_units("FRANCE"), game.get_units("EGYPT")


def test_support_is_cut_by_any_attack_even_a_support_hold_from_elsewhere():
    for escorted in (False, True):
        results, france_units, egypt_units = _play(escorted)
        # nobody moved: both attacks bounced, both supports were cut
        assert france_units == ["F WME", "F ALG"]
        assert egypt_units == ["A LIB", "A TUN", "F MAL"]
        assert "cut" in [str(t) for t in results.get("A TUN", [])]
        assert "cut" in [str(t) for t in results.get("F ALG", [])]
        assert "bounce" in [str(t) for t in results.get("F WME", [])]
        assert "bounce" in [str(t) for t in results.get("A LIB", [])]
