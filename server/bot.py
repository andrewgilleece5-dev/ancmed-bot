"""Map-agnostic heuristic bots.

``DumbBot`` is in the spirit of David Norman's classic DumbBot: score every
province by how good it would be to own (enemy centres weighted by their owner's
size so the leader gets ganged up on; our own centres weighted by how hard
they're being pressed), blur that value across the board, then for every unit
score every legal order by the value of the province it affects and pick
probabilistically. A second pass lets units swap a plain move for *supporting* a
neighbour's move or hold when that is worth more - which is where coordinated
attacks and defence come from, without a hand-written planner.

Every order returned is copied verbatim from ``game.get_all_possible_orders()``,
so the bot can never emit an illegal order.
"""

import math
import random
from collections import defaultdict

from .orders import parse, province


def _convoy_move(order):
    """A '... - X VIA' order: the bot doesn't arrange convoys, so it ignores these."""
    return order.endswith(" VIA")


def _move_target(parsed):
    return parsed["target"] if parsed and parsed.get("action") == "move" else None


class Bot:
    """Base class. ``get_orders`` returns a list of order strings for a power."""

    name = "bot"

    def get_orders(self, game, power_name):  # pragma: no cover - interface only
        raise NotImplementedError


# Difficulty is *behaviour*, not just noise.
#   easy   - follows the value field loosely, ignores defence, blunders often,
#            never coordinates
#   medium - follows the field, supports its attacks, defends its centres
#   hard   - same, but decisive (low temperature), never blunders, defends
#            harder, and commits more units to a break-in
_LEVELS = {
    "easy":   {"temperature": 1.15, "jitter": 0.45, "blunder_rate": 0.22,
               "support": False, "defend_weight": 0.30, "max_supporters": 1},
    "medium": {"temperature": 0.35, "jitter": 0.12, "blunder_rate": 0.0,
               "support": True,  "defend_weight": 1.00, "max_supporters": 2},
    "hard":   {"temperature": 0.16, "jitter": 0.06, "blunder_rate": 0.0,
               "support": True,  "defend_weight": 1.30, "max_supporters": 3},
}


class DumbBot(Bot):
    name = "dumbbot"

    # supply-centre base values
    OWN_BASE = 1.5              # a quiet centre of ours
    THREAT_W = 2.6              # ... + this per enemy unit that can reach it (× defend_weight)
    ATTACK_BASE = 4.0           # any enemy centre
    SIZE_W = 0.45              # ... + this per centre its owner holds (lean on the leader)
    LONE_BONUS = 2.5           # ... + this if the owner is small - finish off the weak
    NEUTRAL_BASE = 4.5          # a neutral centre
    WEAK_W = 2.2                # ... + this per attacker we have beyond its defenders

    # blur: value[p] = best reachable base value decayed per step, plus a lighter
    # diffusion so a cluster of targets outpulls a lone one
    GRADIENT_DECAY = 0.90
    GRADIENT_STEPS = 20
    DIFFUSE_STEPS = 6
    DIFFUSE_ATTEN = 0.35

    STRENGTH_W = 0.30           # our units that can reach a square
    COMPETITION_W = 0.55        # strongest enemy that can reach it
    HOLD_PENALTY = 0.9          # sitting still is worse than advancing
    SUPPORT_MOVE_FACTOR = 1.00  # value of supporting a friendly move (× target value)
    SUPPORT_HOLD_FACTOR = 0.95
    SWITCH_MARGIN = 0.25        # a support must beat the unit's own plan by this

    def __init__(self, seed=None, level="medium"):
        self._rng = random.Random(seed)
        self._adj_by_map = {}
        cfg = _LEVELS.get(level, _LEVELS["medium"])
        self.level = level if level in _LEVELS else "medium"
        self.TEMPERATURE = cfg["temperature"]
        self.JITTER = cfg["jitter"]
        self.blunder_rate = cfg["blunder_rate"]
        self.support = cfg["support"]
        self.defend_weight = cfg["defend_weight"]
        self.MAX_SUPPORTERS = cfg["max_supporters"]

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

    # ---------------------------------------------------------- reachability
    @staticmethod
    def _reach(game, possible):
        """province -> {power -> set(orderable 3-letter loc)} : every square each
        power's units could move to (or hold on), taken straight from the legal
        moves so it always matches the adjudicator."""
        unit_power = {}
        for pw, units in game.get_state()["units"].items():
            for unit in units:
                if not unit.startswith("*"):
                    unit_power[unit[2:]] = pw
        reach = defaultdict(lambda: defaultdict(set))
        for orders in possible.values():
            for order in orders:
                if _convoy_move(order):
                    continue
                tok = order.split()
                if len(tok) < 2 or tok[1] not in unit_power:
                    continue
                pw = unit_power[tok[1]]
                src = tok[1][:3]
                p = parse(order)
                if p["action"] == "move":
                    reach[p["target"]][pw].add(src)
                elif p["action"] == "hold":
                    reach[province(tok[1])][pw].add(src)
        return reach

    # ------------------------------------------------------------ valuation
    def _province_values(self, game, power_name, possible, reach):
        adj = self._adjacency(game)
        state = game.get_state()
        centers = state["centers"]
        sizes = {pw: len(cs) for pw, cs in centers.items()}
        owner = {province(c): pw for pw, cs in centers.items() for c in cs}
        all_sc = {province(s) for s in game.map.scs}
        unit_at = {}
        for pw, units in state["units"].items():
            for unit in units:
                if not unit.startswith("*"):
                    unit_at[province(unit[2:])] = pw

        def strength(p):
            return len(reach.get(p, {}).get(power_name, ()))

        def competition(p):
            r = reach.get(p, {})
            return max((len(v) for e, v in r.items() if e != power_name), default=0)

        def defenders(p):
            o = owner.get(p)
            if not o or o == power_name:
                return 0
            d = 1 if unit_at.get(p) == o else 0
            d += sum(1 for q in adj[p] if unit_at.get(q) == o)
            return d

        base = {}
        for p in adj:
            if p in all_sc:
                o = owner.get(p)
                if o == power_name:
                    base[p] = self.OWN_BASE + self.defend_weight * self.THREAT_W * competition(p)
                elif o:
                    takeable = max(0, strength(p) - defenders(p))
                    osize = sizes.get(o, 0)
                    base[p] = (self.ATTACK_BASE + self.SIZE_W * osize
                               + self.WEAK_W * takeable)
                    if osize <= 4:
                        # a small power - lean toward finishing it off; extra if
                        # we already have force in range
                        base[p] += self.LONE_BONUS * (5 - osize)
                        if strength(p) >= 1:
                            base[p] += self.LONE_BONUS
                else:
                    base[p] = self.NEUTRAL_BASE + self.WEAK_W * max(0, strength(p) - 1)
            else:
                base[p] = 0.0

        # gradient
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

        # diffusion
        prox = dict(base)
        weight = 1.0
        for _ in range(self.DIFFUSE_STEPS):
            prox = {p: (prox[p] + sum(prox[q] for q in adj[p])) / (len(adj[p]) + 1)
                    for p in adj}
            weight *= self.DIFFUSE_ATTEN
            for p in adj:
                value[p] += weight * prox[p]

        for p in adj:
            value[p] += (self.STRENGTH_W * strength(p)
                         - self.COMPETITION_W * competition(p)
                         + self._rng.uniform(-self.JITTER, self.JITTER))
        return value

    # -------------------------------------------------------------- dispatch
    def get_orders(self, game, power_name):
        if game.phase_type == "M":
            return self._movement(game, power_name)
        if game.phase_type == "R":
            return self._retreats(game, power_name)
        if game.phase_type == "A":
            return self._adjustments(game, power_name)
        return []

    # -------------------------------------------------------------- movement
    def _weighted_choice(self, scored):
        """scored: list of (score, order, parsed); sorts best-first, softmax-samples."""
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
                return order, parsed
        return top[0][1], top[0][2]

    def _movement(self, game, power_name):
        possible = game.get_all_possible_orders()
        reach = self._reach(game, possible)
        values = self._province_values(game, power_name, possible, reach)

        order_locs = game.get_orderable_locations(power_name)
        own_here = {province(loc) for loc in order_locs}
        loc_at = {province(loc): loc for loc in order_locs}

        def opts(loc):
            return possible.get(loc, [])

        # which convoy moves we can escort: {(src, dst): [fleet loc that can convoy]}
        convoy_escorts = defaultdict(list)
        for loc in order_locs:
            for o in opts(loc):
                cp = parse(o)
                if cp["action"] == "convoy":
                    convoy_escorts[(cp["from"], cp["target"])].append(loc)

        # ---- pass 1: every unit picks a plain move / hold ----------------
        plan = {}          # loc -> parsed order
        order_of = {}      # loc -> order string
        entering = {}      # province -> set(source loc) of our units moving in
        escorting = {}     # fleet loc -> convoy order it must play

        def best_gain(loc):
            here = province(loc)
            mv = [values.get(parse(o)["target"], 0.0)
                  for o in opts(loc) if parse(o)["action"] == "move"]
            return (max(mv) if mv else 0.0) - values.get(here, 0.0)

        for loc in sorted(order_locs, key=best_gain, reverse=True):
            if loc in escorting:
                continue
            options = opts(loc)
            if not options:
                continue
            here = province(loc)
            scored = []
            for order in options:
                p = parse(order)
                if p["action"] == "move":
                    tgt = p["target"]
                    if _convoy_move(order):
                        free = [f for f in convoy_escorts.get((here, tgt), [])
                                if f not in plan and f not in escorting and f != loc]
                        s = values.get(tgt, 0.0) - 0.5 if free else -50.0
                    elif tgt in entering or plan.get(loc_at.get(tgt), {}).get("target") == here:
                        s = -50.0                      # our own units would bounce
                    elif tgt in own_here and tgt != here and not _is_vacating(loc_at.get(tgt), plan):
                        s = -50.0
                    else:
                        s = values.get(tgt, 0.0)
                elif p["action"] == "hold":
                    s = values.get(here, 0.0) - self.HOLD_PENALTY
                else:
                    s = -20.0                          # supports handled in pass 2
                scored.append((s, order, p))
            order, p = self._weighted_choice(scored)
            if self.blunder_rate and self._rng.random() < self.blunder_rate:
                order = self._rng.choice([o for o in options if not _convoy_move(o)] or options)
                p = parse(order)
            plan[loc], order_of[loc] = p, order
            if p["action"] == "move":
                entering.setdefault(p["target"], set()).add(here)
                if _convoy_move(order):
                    need = 1
                    for f in convoy_escorts.get((here, p["target"]), []):
                        if need <= 0:
                            break
                        if f in plan or f in escorting or f == loc:
                            continue
                        cvy = next((o for o in opts(f) if parse(o)["action"] == "convoy"
                                    and parse(o)["from"] == here
                                    and parse(o)["target"] == p["target"]), None)
                        if cvy:
                            escorting[f] = cvy
                            order_of[f] = cvy
                            plan[f] = parse(cvy)
                            need -= 1

        # ---- pass 2: back the best attacks / defend held centres --------
        if self.support:
            # anchor moves: the province each unit is moving into, kept fixed so
            # supporters have something real to point at
            anchor_mover = {}   # province -> the one loc whose move we support
            for loc, p in plan.items():
                if p["action"] == "move":
                    anchor_mover.setdefault(p["target"], loc)
            supported = defaultdict(int)

            for loc in sorted(order_locs,
                              key=lambda l: values.get(_move_target(plan.get(l)), 0.0)
                              if plan.get(l, {}).get("action") == "move"
                              else values.get(province(l), 0.0)):
                if loc not in plan or loc in escorting:
                    continue
                here = province(loc)
                cur = plan[loc]
                # never pull a unit off an anchor move that others rely on
                if cur["action"] == "move" and anchor_mover.get(cur["target"]) == loc:
                    continue
                cur_val = (values.get(cur["target"], 0.0) if cur["action"] == "move"
                           else values.get(here, 0.0) - self.HOLD_PENALTY)
                best = (None, None, cur_val + self.SWITCH_MARGIN)
                for order in opts(loc):
                    p = parse(order)
                    if p["action"] == "support_move":
                        tgt, src = p["target"], p["from"]
                        if anchor_mover.get(tgt) is None or province(anchor_mover[tgt]) != src:
                            continue
                        if supported[tgt] >= self.MAX_SUPPORTERS:
                            continue
                        v = values.get(tgt, 0.0) * self.SUPPORT_MOVE_FACTOR
                        if v > best[2]:
                            best = (order, p, v)
                    elif p["action"] == "support_hold":
                        tgt = p["target"]
                        holder = loc_at.get(tgt)
                        if (holder is None or holder not in plan
                                or plan[holder]["action"] == "move"):
                            continue
                        if supported[tgt] >= self.MAX_SUPPORTERS:
                            continue
                        v = values.get(tgt, 0.0) * self.SUPPORT_HOLD_FACTOR
                        if v > best[2]:
                            best = (order, p, v)
                if best[0]:
                    if cur["action"] == "move":
                        entering.get(cur["target"], set()).discard(here)
                    plan[loc], order_of[loc] = best[1], best[0]
                    supported[best[1]["target"]] += 1

            # cleanup: drop any support that no longer points at a real action
            movers = {p["target"] for p in plan.values() if p["action"] == "move"}
            for loc, p in list(plan.items()):
                if p["action"] == "support_move" and p["target"] not in movers:
                    order_of[loc] = self._fallback(loc, opts(loc), plan)
                    plan[loc] = parse(order_of[loc])
                elif p["action"] == "support_hold":
                    holder = loc_at.get(p["target"])
                    if not holder or plan.get(holder, {}).get("action") == "move":
                        order_of[loc] = self._fallback(loc, opts(loc), plan)
                        plan[loc] = parse(order_of[loc])

        return list(order_of.values())

    @staticmethod
    def _fallback(loc, options, plan):
        """A safe order for a unit whose support just got invalidated: hold if we
        can, else an unobstructed move, else anything legal."""
        hold = next((o for o in options if parse(o)["action"] == "hold"), None)
        if hold:
            return hold
        taken = {p["target"] for p in plan.values() if p.get("action") == "move"}
        move = next((o for o in options
                     if parse(o)["action"] == "move" and not _convoy_move(o)
                     and parse(o)["target"] not in taken), None)
        return move or options[0]

    # -------------------------------------------------------------- retreats
    def _retreats(self, game, power_name):
        possible = game.get_all_possible_orders()
        reach = self._reach(game, possible)
        values = self._province_values(game, power_name, possible, reach)
        orders = []
        for loc in game.get_orderable_locations(power_name):
            options = possible.get(loc, [])
            retreats = [o for o in options if parse(o)["action"] == "retreat"]
            if retreats:
                orders.append(max(
                    retreats,
                    key=lambda o: values.get(parse(o)["target"], 0.0)
                    + self._rng.uniform(0.0, self.JITTER)))
            else:
                disbands = [o for o in options if parse(o)["action"] == "disband"]
                if disbands:
                    orders.append(disbands[0])
        return orders

    # ----------------------------------------------------------- adjustments
    def _adjustments(self, game, power_name):
        possible = game.get_all_possible_orders()
        reach = self._reach(game, possible)
        values = self._province_values(game, power_name, possible, reach)
        state = game.get_state()
        build = state["builds"][power_name]
        count = build["count"]
        orders = []

        if count > 0:
            sites = sorted(build["homes"],
                           key=lambda s: values.get(province(s), 0.0), reverse=True)
            for site in sites:
                if len(orders) >= count:
                    break
                builds = [o for key, o_list in possible.items()
                          if province(key) == province(site)
                          for o in o_list if parse(o)["action"] == "build"]
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
                disbands = [o for o in possible.get(loc, [])
                            if parse(o)["action"] == "disband"]
                if disbands:
                    orders.append(disbands[0])
        return orders


def _is_vacating(loc, plan):
    """True if `loc` holds a unit of ours that pass 1 has moving away."""
    return bool(loc and loc in plan and plan[loc]["action"] == "move")


_ALIASES = {"dumbbot": "medium"}


def make_bot(name="medium", seed=None):
    """`name` is a difficulty ('easy' / 'medium' / 'hard'); 'dumbbot' (the v1
    value stored in old games) maps to 'medium'."""
    level = _ALIASES.get(name, name)
    if level not in _LEVELS:
        level = "medium"
    return DumbBot(seed=seed, level=level)
