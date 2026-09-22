"""Static per-map data the `diplomacy` package doesn't carry.

``SVG_ID_ALIASES`` - the engine's supply-centre codes don't always match the
polygon ids in the packaged map SVG, so the renderer silently fails to colour
those provinces. Maps ``engine code -> svg polygon id (without the leading _)``.

``HOME_TERRITORY`` - the engine models a power as only its home supply centres,
but the physical boards colour a nation's non-SC homeland too (Saxony is German,
Navarra is Spanish, ...). Only the Modern map has meaningful non-SC national
land; ``standard`` and ``ancmed`` home territory is exactly the home SCs.
Modern assignments are the provinces that border only that nation's home SCs
(and sea/impassable), matching the Modern Diplomacy board.
"""

SVG_ID_ALIASES = {
    # Water provinces are deliberately not listed here even where their engine
    # code also mismatches the SVG id (e.g. modern's NAO/SAO/MID are drawn as
    # "_nat"/"_sat"/"_mat") - the renderer never colours water by ownership
    # (see render._fix_svg_id_aliases), so there is nothing to fix for them.
    "modern": {
        "LIV": "lpl",   # Liverpool
        "SVE": "svl",   # Seville
    },
}

HOME_TERRITORY = {
    "modern": {
        "BRITAIN": ["WAL", "YOR", "CLY"],
        "FRANCE": ["BRI", "PIC", "AUV"],
        "GERMANY": ["RUH", "SAX"],
        "SPAIN": ["NAV", "ADL"],
        "ITALY": ["PIE", "TUS", "APU"],
        "POLAND": ["SIL", "PRU"],
        "RUSSIA": ["CRP", "VOL", "URA", "SIB"],
        "UKRAINE": ["POD", "DON"],
        "TURKEY": ["ANA"],
        "EGYPT": ["SIN"],
    },
    "standard": {},
    "ancmed": {},
    "pure": {},
}
