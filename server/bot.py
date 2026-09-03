"""Map-agnostic heuristic bots.

``DumbBot`` follows the spirit of David Norman's classic DumbBot: it never looks
ahead, it just scores every province by how good it would be to own (weighted by
nearby supply centres and who holds them), smears that value across the board so
units drift toward valuable clusters, and then plays, for each unit, the legal
order that lands on the best province. A light coordination pass adds supports
for the strongest contested moves.

Every order returned is copied verbatim from
``game.get_all_possible_orders()``, so the bot can never emit an illegal order.
All inputs come from ``game`` / ``game.map``, so the same code works on
``ancmed``, ``standard``, ``pure``, ``modern`` or any other loaded map.
"""

import math
import random
from collections import defaultdict

from .orders import parse, province


class Bot:
    """Base class. ``get_orders`` returns a list of order strings for a power."""

    name = "bot"

    def get_orders(self, game, power_name):  # pragma: no cover - interface only
        raise NotImplementedError


class DumbBot(Bot):
    name = "dumbbot"

    # A province's value is the value of the best supply centre reachable from
    # it, discounted by GRADIENT_DECAY per step of distance. That makes a smooth
    # potential field: from any square at least one neighbour is worth more, so
    # units keep climbing toward the most valuable target instead of camping.
    GRADIENT_DECAY = 0.86
    GRADIENT_STEPS = 12

    ENEMY_SC = 2.0
    NEUTRAL_SC = 1.6
    OWN_SC_SAFE = 0.25          # already ours and quiet: don't sit on it
    OWN_SC_THREATENED = 2.4     # ours with an enemy next door: defend it
    NON_SC_BASE = 0.05

    STRENGTH_FACTOR = 0.22      # our nearby units make an attack more appealing
    COMPETITION_FACTOR = 0.35   # enemy nearby units make it riskier
    JITTER = 0.12
    TEMPERATURE = 0.28          # softmax temperature for move selection
    HOLD_PENALTY = 0.30
    SUPPORT_SWITCH_MARGIN = 0.30  # value a support must beat a unit's own plan by

    def __init__(self, seed=None):
        self._rng = random.Random(seed)
        self._adj_by_map = {}

    # ------------------------------------------------------------------ graph
    def _adjacency(self, game):
        """province -> set(province), built once per map name."""
        cached = self._adj_by_map.get(game.map.name)
        if cached is not None:
            return cached

        provinces = {province(loc) for loc in game.map.locs}
        adj = {p: set() for p in provinces}
        for loc in game.map.locs:
            here = province(loc)
            for other in game.map.abut_list(loc, incl_no_coast=True):
                there = province(other)
                if there in provinces and there != here:
                    adj[here].add(there)
        self._adj_by_map[game.map.name] = adj
        return adj

    # ------------------------------------------------------------ valuation
    def _province_values(self, game, power_name):
        adj = self._adjacency(game)
        state = game.get_state()

        sc_owner = {}
        for pw, centers in state["centers"].items():
            for center in centers:
                sc_owner[province(center)] = pw
        all_scs = {province(s) for s in game.map.scs}

        unit_at = {}  # province -> power holding a (non-dislodged) unit there
        for pw, units in state["units"].items():
            for unit in units:
                if not unit.startswith("*"):
                    unit_at[province(unit[2:])] = pw

        # intrinsic worth of each province (its own supply-centre value)
        base = {}
        for p in adj:
            if p in all_scs:
                owner = sc_owner.get(p)
                if owner is None:
                    base[p] = self.NEUTRAL_SC
                elif owner != power_name:
                    base[p] = self.ENEMY_SC
                elif any(unit_at.get(q) not in (None, power_name) for q in adj[p]):
                    base[p] = self.OWN_SC_THREATENED
                else:
                    base[p] = self.OWN_SC_SAFE
            else:
                base[p] = self.NON_SC_BASE

        # potential field: value[p] = best reachable base value, decayed by distance
        value = dict(base)
        for _ in range(self.GRADIENT_STEPS):
            changed = False
            for p in adj:
                if not adj[p]:
                    continue
                spread = self.GRADIENT_DECAY * max(value[q] for q in adj[p])
                if spread > value[p] + 1e-9:
                    value[p] = spread
                    changed = True
            if not changed:
                break

        # local force balance + a little noise so games diverge
        for p in adj:
            ring = list(adj[p]) + [p]
            own = sum(1 for q in ring if unit_at.get(q) == power_name)
            enemy_counts = defaultdict(int)
            for q in ring:
                holder = unit_at.get(q)
                if holder is not None and holder != power_name:
                    enemy_counts[holder] += 1
            enemy = max(enemy_counts.values()) if enemy_counts else 0
            value[p] += self.STRENGTH_FACTOR * own - self.COMPETITION_FACTOR * enemy
            value[p] += self._rng.uniform(-self.JITTER, self.JITTER)

        return value

    # -------------------------------------------------------------- dispatch
    def get_orders(self, game, power_name):
        phase_type = game.phase_type
        if phase_type == "M":
            return self._movement(game, power_name)
        if phase_type == "R":
            return self._retreats(game, power_name)
        if phase_type == "A":
            return self._adjustments(game, power_name)
        return []

    # -------------------------------------------------------------- movement
    def _weighted_choice(self, scored):
        """scored: list of (score, order, parsed). Softmax-sample the top few."""
        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:4]
        best = top[0][0]
        weights = [math.exp((s - best) / max(self.TEMPERATURE, 1e-3)) for s, _, _ in top]
        total = sum(weights) or 1.0
        pick = self._rng.random() * total
        acc = 0.0
        for (score, order, parsed), weight in zip(top, weights):
            acc += weight
            if pick <= acc:
                return score, order, parsed
        return top[0]

    def _movement(self, game, power_name):
        values = self._province_values(game, power_name)
        possible = game.get_all_possible_orders()

        order_locs = game.get_orderable_locations(power_name)
        own_locs = [province(loc) for loc in order_locs]

        def best_option_value(loc):
            best = -9.0
            for order in possible.get(loc, []):
                p = parse(order)
                if p["action"] == "move":
                    best = max(best, values.get(p["target"], 0.0))
                elif p["action"] == "hold":
                    best = max(best, values.get(province(loc), 0.0))
            return best

        # Let the units with the most to gain pick first; others adapt around them.
        order_locs = sorted(order_locs, key=best_option_value, reverse=True)

        chosen = {}        # loc -> order string
        move_target = {}   # loc -> province being entered, or None
        claimed = set()    # provinces already taken as a destination by our units
        for loc in order_locs:
            options = possible.get(loc, [])
            if not options:
                continue
            here = province(loc)
            scored = []
            for order in options:
                p = parse(order)
                if p["action"] == "move":
                    tgt = p["target"]
                    score = values.get(tgt, 0.0)
                    # avoid our own units bouncing off each other: another unit
                    # already heading there, a direct swap, or a stationary friend.
                    if tgt in claimed:
                        score -= 3.0
                    elif move_target.get(tgt) == here:
                        score -= 3.0
                    elif tgt in own_locs and tgt != here:
                        score -= 2.5
                elif p["action"] == "hold":
                    score = values.get(here, 0.0) - self.HOLD_PENALTY
                else:
                    score = -9.0  # support/convoy: only if nothing else exists
                scored.append((score, order, p))
            _, order, p = self._weighted_choice(scored)
            chosen[loc] = order
            target = p["target"] if p["action"] == "move" else None
            move_target[loc] = target
            if target:
                claimed.add(target)

        self._add_supports(power_name, values, possible, chosen, move_target)
        return list(chosen.values())

    def _add_supports(self, power_name, values, possible, chosen, move_target):
        our_moves = defaultdict(list)  # target province -> [source province]
        for loc, target in move_target.items():
            if target:
                our_moves[target].append(province(loc))
        holders = {province(loc) for loc, target in move_target.items() if target is None}

        for loc in list(chosen):
            here = province(loc)
            current_target = move_target[loc]
            current_value = (
                values.get(current_target, 0.0)
                if current_target
                else values.get(here, 0.0)
            )
            best_order = None
            best_value = current_value + self.SUPPORT_SWITCH_MARGIN

            for order in possible.get(loc, []):
                p = parse(order)
                if p["action"] == "support_move":
                    target, src = p["target"], p["from"]
                    if src == here:
                        continue
                    if any(m == src for m in our_moves.get(target, [])):
                        if values.get(target, 0.0) > best_value:
                            best_order, best_value = order, values.get(target, 0.0)
                elif p["action"] == "support_hold":
                    target = p["target"]
                    if target in holders and target != here:
                        # support a neighbour sitting on a valuable/own centre
                        support_value = values.get(target, 0.0) * 0.85
                        if support_value > best_value:
                            best_order, best_value = order, support_value

            if best_order:
                chosen[loc] = best_order
                move_target[loc] = None

    # -------------------------------------------------------------- retreats
    def _retreats(self, game, power_name):
        values = self._province_values(game, power_name)
        possible = game.get_all_possible_orders()
        orders = []
        for loc in game.get_orderable_locations(power_name):
            options = possible.get(loc, [])
            retreats = [o for o in options if parse(o)["action"] == "retreat"]
            if retreats:
                orders.append(
                    max(
                        retreats,
                        key=lambda o: values.get(parse(o)["target"], 0.0)
                        + self._rng.uniform(0.0, self.JITTER),
                    )
                )
            else:
                disbands = [o for o in options if parse(o)["action"] == "disband"]
                if disbands:
                    orders.append(disbands[0])
        return orders

    # ----------------------------------------------------------- adjustments
    def _adjustments(self, game, power_name):
        values = self._province_values(game, power_name)
        possible = game.get_all_possible_orders()
        state = game.get_state()
        build = state["builds"][power_name]
        count = build["count"]
        orders = []

        if count > 0:
            sites = sorted(
                build["homes"], key=lambda s: values.get(province(s), 0.0), reverse=True
            )
            for site in sites:
                if len(orders) >= count:
                    break
                builds = [
                    o
                    for key, opts in possible.items()
                    if province(key) == province(site)
                    for o in opts
                    if parse(o)["action"] == "build"
                ]
                if not builds:
                    continue
                fleets = [o for o in builds if o.split()[0] == "F"]
                armies = [o for o in builds if o.split()[0] == "A"]
                loc_type = game.map.loc_type.get(province(site), "")
                if loc_type in ("COAST", "PORT") and fleets:
                    orders.append(fleets[0])
                elif armies:
                    orders.append(armies[0])
                elif fleets:
                    orders.append(fleets[0])

        elif count < 0:
            units = [u for u in state["units"][power_name] if not u.startswith("*")]
            weakest = sorted(units, key=lambda u: values.get(province(u[2:]), 0.0))
            for unit in weakest[: -count]:
                loc = unit[2:5]
                disbands = [
                    o for o in possible.get(loc, []) if parse(o)["action"] == "disband"
                ]
                if disbands:
                    orders.append(disbands[0])

        return orders


BOTS = {"dumbbot": DumbBot}


def make_bot(name="dumbbot", seed=None):
    return BOTS.get(name, DumbBot)(seed=seed)
