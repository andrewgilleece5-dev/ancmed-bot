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
    "modern": {
        "LIV": "lpl",   # Liverpool
        "SVE": "svl",   # Seville
        "NAO": "nat",   # North Atlantic
        "SAO": "sat",   # South Atlantic
        "MID": "mat",   # Mid-Atlantic
    },
}

HOME_TERRITORY = {
    "modern": {
        "BRITAIN": ["WAL", "YOR", "CLY"],
        "FRANCE": ["BRI", "PIC", "AUV"],
        "GERMANY": ["RUH", "SAX"],
        "SPAIN": ["NAV", "ADL"],
        "ITALY": ["PIE", "TUS", "APU"],
        "POLAND": ["SIL"],
        "RUSSIA": ["CRP", "VOL", "URA", "SIB"],
        "UKRAINE": ["POD", "DON"],
        "TURKEY": ["ANA"],
        "EGYPT": ["SIN"],
    },
    "standard": {},
    "ancmed": {},
    "pure": {},
}
