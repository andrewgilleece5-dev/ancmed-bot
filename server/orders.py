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
        return {"action": "convoy", "loc": province(unit_loc), "target": province(tok[-1])}
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
