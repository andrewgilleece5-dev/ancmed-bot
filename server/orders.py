"""Tiny parser for the diplomacy engine's human-readable order strings.

The engine hands us orders already formatted as strings such as::

    A ROM H
    A ROM - VEN
    F SPA/NC - LYO
    F NEA S A ROM - APU
    F NEA S A ROM
    F ION C A TUN - SYR
    A ROM R VEN
    A ROM D
    F SPA/SC B
    WAIVE

We never build order strings ourselves - we only ever pick one of the strings
the engine already told us is legal - so this parser just needs to classify a
string and pull out the province(s) involved for scoring.
"""


def province(loc):
    """Strip a coast qualifier (``SPA/NC`` -> ``SPA``) and upper-case."""
    return loc.split("/")[0].upper()


def parse(order):
    """Return a dict describing ``order``. Always has an ``action`` key."""
    if not order or order == "WAIVE":
        return {"action": "waive"}

    tok = order.split()
    if len(tok) < 3:
        return {"action": "other"}

    unit_loc = tok[1]
    verb = tok[2]

    if verb == "H":
        return {"action": "hold", "loc": province(unit_loc)}
    if verb == "D":
        return {"action": "disband", "loc": province(unit_loc)}
    if verb == "B":
        return {"action": "build", "loc": province(unit_loc), "unit_type": tok[0]}
    if verb == "-":
        return {"action": "move", "loc": province(unit_loc), "target": province(tok[3])}
    if verb == "R":
        return {"action": "retreat", "loc": province(unit_loc), "target": province(tok[3])}
    if verb == "C":
        # "C <type> <from> - <to>"
        src = province(tok[4]) if len(tok) > 4 else None
        return {
            "action": "convoy",
            "loc": province(unit_loc),
            "from": src,
            "target": province(tok[-1]),
        }
    if verb == "S":
        # "S <type> <loc>"  (support hold)  or  "S <type> <loc> - <loc>" (support move)
        if "-" in tok:
            dash = tok.index("-")
            return {
                "action": "support_move",
                "loc": province(unit_loc),
                "from": province(tok[4]),
                "target": province(tok[dash + 1]),
            }
        return {"action": "support_hold", "loc": province(unit_loc), "target": province(tok[4])}

    return {"action": "other"}


# --------------------------------------------------------------------------- #
#  Friendly order tree                                                         #
# --------------------------------------------------------------------------- #
# The frontend renders one row per unit: a primary <select> of action types,
# and (when the action needs one) a secondary <select> of full province names.
# Every leaf carries the exact engine order string, so nothing is re-assembled
# client-side.

_ACTION_ORDER = [
    "hold", "move", "support_hold", "support_move", "convoy",
    "retreat", "disband", "build_army", "build_fleet", "waive",
]


def _dest_token(order):
    """The destination token of a move/retreat, keeping any coast (`SPA/NC`)."""
    tok = order.split()
    for kw in ("-", "R"):
        if kw in tok:
            return tok[tok.index(kw) + 1]
    return tok[-1]


def _name(province_name, code):
    """'ION' -> 'Ionian Sea (ION)'; 'SPA/NC' -> 'Spain (SPA/NC)'. The parenthetical
    matches the abbreviation printed on the board."""
    base = code.split("/")[0]
    full = (province_name(base) if province_name else None)
    if not full:
        return code.upper()
    return "%s (%s)" % (full, code.upper())


def order_tree(loc, options, phase_type, province_name=None):
    """Build the friendly action tree for one orderable location.

    `options` is `game.get_all_possible_orders()[loc]`; `province_name` maps a
    3-letter code to a full name (or returns None).
    """
    grouped = {}
    for order in options:
        grouped.setdefault(parse(order)["action"], []).append(order)

    is_build_site = phase_type == "A" and "build" in grouped
    non_waive = [o for o in options if o != "WAIVE"]
    unit = "" if is_build_site else (" ".join(non_waive[0].split()[:2]) if non_waive else "")

    actions = []

    def add_leaf(kind, order):
        actions.append({"type": kind, "order": order})

    def targets(orders, dest_of):
        seen, out = set(), []
        for o in sorted(orders):
            dest = dest_of(o)
            if dest in seen:
                continue
            seen.add(dest)
            out.append({"label": _name(province_name, dest), "order": o})
        return out

    if phase_type == "M":
        if grouped.get("hold"):
            add_leaf("hold", grouped["hold"][0])
        if grouped.get("move"):
            actions.append({"type": "move", "targets": targets(grouped["move"], _dest_token)})
        if grouped.get("support_hold"):
            actions.append({
                "type": "support_hold",
                "targets": targets(grouped["support_hold"], lambda o: parse(o)["target"]),
            })
        for kind in ("support_move", "convoy"):
            if grouped.get(kind):
                moves = []
                for o in sorted(grouped[kind]):
                    p = parse(o)
                    moves.append({
                        "label": "%s → %s" % (
                            _name(province_name, p["from"]), _name(province_name, p["target"])),
                        "order": o,
                    })
                actions.append({"type": kind, "moves": moves})

    elif phase_type == "R":
        if grouped.get("retreat"):
            actions.append({"type": "retreat", "targets": targets(grouped["retreat"], _dest_token)})
        if grouped.get("disband"):
            add_leaf("disband", grouped["disband"][0])

    elif phase_type == "A":
        if is_build_site:
            armies = [o for o in grouped["build"] if o.split()[0] == "A"]
            fleets = [o for o in grouped["build"] if o.split()[0] == "F"]
            if armies:
                add_leaf("build_army", armies[0])
            if len(fleets) == 1:
                add_leaf("build_fleet", fleets[0])
            elif fleets:
                actions.append({
                    "type": "build_fleet",
                    "targets": [{"label": _name(province_name, o.split()[1]), "order": o}
                                for o in sorted(fleets)],
                })
            add_leaf("waive", "WAIVE")
        if grouped.get("disband"):
            add_leaf("disband", grouped["disband"][0])
            add_leaf("keep", "")

    actions.sort(key=lambda a: _ACTION_ORDER.index(a["type"]) if a["type"] in _ACTION_ORDER else 99)

    if unit:
        kind = "Fleet" if unit.split()[0] == "F" else "Army"
        label = "%s in %s" % (kind, _name(province_name, loc))
    else:
        label = "Build in %s" % _name(province_name, loc)

    return {"loc": loc, "unit": unit, "label": label, "actions": actions}
