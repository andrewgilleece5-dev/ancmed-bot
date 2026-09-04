"""Board rendering: the engine's SVG plus two fixes it doesn't do itself.

1. Colour supply centres whose engine code doesn't match the packaged SVG's
   polygon id (Seville, Liverpool on the Modern map - see `territory.py`).
2. Tint each power's non-SC home territory from turn one.

Also renders any *historical* phase (position + the orders that were given, drawn
as arrows) by replaying that phase into a throwaway game.
"""

import re

from diplomacy import Game
from diplomacy.engine.renderer import Renderer

from .territory import HOME_TERRITORY, SVG_ID_ALIASES


def render_board(game, map_name, phase=None):
    """Return the SVG for the current position, or for a historical `phase`
    (a `GamePhaseData` from `game.get_phase_history()`)."""
    try:
        if phase is not None:
            svg = _render_phase(map_name, phase)
            state = phase.state
        else:
            svg = game.render(incl_orders=True, incl_abbrev=False)
            state = game.get_state()
    except Exception:
        # never let a rendering problem take down the API
        return game.render(incl_orders=True) if phase is None else ""

    try:
        svg = _fix_svg_id_aliases(svg, map_name, state)
        svg = _tint_home_territory(svg, map_name, state)
    except Exception:
        pass
    return svg


def _render_phase(map_name, phase):
    tmp = Game(map_name=map_name)
    tmp.set_state(phase.state)
    for power, orders in (phase.orders or {}).items():
        if orders:
            try:
                tmp.set_orders(power, orders)
            except Exception:
                pass
    return Renderer(tmp).render(incl_orders=True, incl_abbrev=False)


# --------------------------------------------------------------------- helpers
def _province(loc):
    return loc.split("/")[0].upper()


def _influenced(state):
    out = set()
    for locs in state.get("influence", {}).values():
        out.update(_province(loc) for loc in locs)
    return out


def _owner(state, code):
    for group in ("influence", "centers"):
        for power, locs in state.get(group, {}).items():
            if any(_province(loc) == code for loc in locs):
                return power
    return None


def _set_class(svg, svg_id, css_class, only_if=None):
    """Set the `class` of the SVG element with id `_<svg_id>`. If `only_if` is
    given, only change it when the current class equals that value."""
    match = re.search(r'<(?:polygon|path|g)\b[^>]*\bid="_%s"[^>]*>' % re.escape(svg_id), svg)
    if not match:
        return svg
    tag = match.group(0)
    cur = re.search(r'\bclass="([^"]*)"', tag)
    if cur:
        if only_if is not None and cur.group(1) != only_if:
            return svg
        new_tag = tag[: cur.start()] + 'class="%s"' % css_class + tag[cur.end():]
    else:
        if only_if is not None:
            return svg
        new_tag = tag[:-1] + ' class="%s">' % css_class
    return svg[: match.start()] + new_tag + svg[match.end():]


def _fix_svg_id_aliases(svg, map_name, state):
    for code, svg_id in SVG_ID_ALIASES.get(map_name, {}).items():
        owner = _owner(state, code)
        if owner:
            svg = _set_class(svg, svg_id, owner.lower())
    return svg


def _tint_home_territory(svg, map_name, state):
    occupied = _influenced(state)
    for power, provinces in HOME_TERRITORY.get(map_name, {}).items():
        for prov in provinces:
            if prov not in occupied:
                svg = _set_class(svg, prov.lower(), power.lower(), only_if="nopower")
    return svg
