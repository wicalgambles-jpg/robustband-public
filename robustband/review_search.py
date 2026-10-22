# SPDX-License-Identifier: MIT
"""Exact-integer, budgeted optimization of finite-record review width.

The complement is a unit-profit multidimensional knapsack: retain as many
unreviewed items as possible. Surrogate capacity bounds and interchangeable
contribution groups accelerate search. These are established optimization tools.
No floating-point relaxation or guessed review response enters a certificate.
"""
from itertools import combinations
from math import lcm
from fractions import Fraction as F

from .review_dual import price_directions, scalar_bound


def optimize_widths(rows, epsilon, node_budget, exchange_budget, pricing_rounds=0):
    """Return selected indices, a proven cardinality lower bound, and diagnostics.

    Inputs are nonnegative Fraction rows and epsilon. The caller validates the
    review problem and budget. Integer scaling preserves all feasibility tests.
    The incumbent includes the original minimax-greedy set, so review count
    cannot exceed that baseline. Frontier bounds remain valid on budget cutoff.
    """
    scale = lcm(epsilon.denominator, *(v.denominator for row in rows for v in row))
    matrix = [tuple(int(v * scale) for v in row) for row in rows]
    capacity = int(epsilon * scale)
    n_items = len(matrix[0])

    # Reproduce the legacy greedy ordering using exact integers, including ties.
    residual = [sum(row) for row in matrix]
    totals = [sum(row[i] for row in matrix) for i in range(n_items)]
    left = {i for i in range(n_items) if any(row[i] for row in matrix)}
    selected = set()
    while max(residual) > capacity:
        current = max(residual)
        pick = max(left, key=lambda i: (
            current - max(r - row[i] for r, row in zip(residual, matrix)),
            totals[i], -i))
        selected.add(pick)
        left.remove(pick)
        residual = [r - row[pick] for r, row in zip(residual, matrix)]

    # Nonbinding, duplicate and componentwise weaker rows need no search.
    tight = list(dict.fromkeys(row for row in matrix if sum(row) > capacity))
    tight = [row for row in tight if not any(
        other != row and all(a <= b for a, b in zip(row, other)) for other in tight)]
    active = [i for i in range(n_items) if any(row[i] for row in tight)]
    columns = {i: tuple(row[i] for row in tight) for i in active}
    m = len(tight)
    pools = [(j,) for j in range(m)]
    if m > 1:
        pools += list(combinations(range(m), 2)) if m <= 8 else []
        pools = list(dict.fromkeys(pools + [tuple(range(m))]))

    def pack(order, initial=()):
        kept = list(initial)
        kept_set = set(kept)
        loads = [sum(columns[i][j] for i in kept) for j in range(m)]
        for i in order:
            if i not in kept_set and all(a + b <= capacity for a, b in zip(loads, columns[i])):
                kept.append(i)
                kept_set.add(i)
                loads = [a + b for a, b in zip(loads, columns[i])]
        return tuple(sorted(kept))

    order = sorted(active, key=lambda i: (max(columns[i]), sum(columns[i]), i))
    best = pack(order, (i for i in active if i not in selected))
    for pool in pools:
        candidate = pack(sorted(active, key=lambda i: (
            sum(columns[i][j] for j in pool), max(columns[i]), i)))
        if len(candidate) > len(best):
            best = candidate

    grouped = {}
    for i in order:
        grouped.setdefault(columns[i], []).append(i)
    groups = [(column, tuple(ids)) for column, ids in grouped.items()]
    suffix = [0] * (len(groups) + 1)
    for pos in range(len(groups) - 1, -1, -1):
        suffix[pos] = suffix[pos + 1] + len(groups[pos][1])
    # Any nonnegative sum of constraints is a necessary scalar constraint.
    # Cheapest scalar contributions give an upper bound on the number retained.
    surrogates = [(pool, sorted((sum(column[j] for j in pool), g, len(ids))
                              for g, (column, ids) in enumerate(groups))) for pool in pools]
    priced_surrogates = []

    def upper_bound(pos, caps, count):
        upper = count + suffix[pos]
        for pool, costs in surrogates:
            available = sum(caps[j] for j in pool)
            extra = 0
            for cost, g, multiplicity in costs:
                if g < pos:
                    continue
                take = multiplicity if cost == 0 else min(multiplicity, available // cost)
                extra += take
                available -= take * cost
                if take < multiplicity:
                    break
            upper = min(upper, count + extra)
            if upper <= len(best):
                break
        for weights, costs in priced_surrogates:
            available = sum(a * p for a, p in zip(caps, weights))
            extra = 0
            for cost, g, multiplicity in costs:
                if g < pos:
                    continue
                take = multiplicity if cost == 0 else min(multiplicity, available // cost)
                extra += take
                available -= take * cost
                if take < multiplicity:
                    break
            upper = min(upper, count + extra)
            if upper <= len(best):
                break
        return upper

    caps = (capacity,) * m
    root_upper = upper_bound(0, caps, 0)
    portfolio_reviews = len(active) - len(best)
    checks = 0
    # A feasible one-for-two exchange reduces reviews by one. Bound the number
    # of exact vector comparisons, and stop when the root bound is attained.
    while len(best) < root_upper and checks < exchange_budget:
        loads = tuple(sum(columns[i][j] for i in best) for j in range(m))
        excluded = [i for i in order if i not in best]
        removal_order = sorted(best, key=lambda i: (-sum(columns[i]), i))
        improvement = None
        for a, b in combinations(excluded, 2):
            need = tuple(columns[a][j] + columns[b][j] + loads[j] - capacity for j in range(m))
            for removed in removal_order:
                if checks == exchange_budget:
                    break
                checks += 1
                if all(v >= d for v, d in zip(columns[removed], need)):
                    improvement = removed, a, b
                    break
            if improvement is not None or checks == exchange_budget:
                break
        if improvement is None:
            break
        removed, a, b = improvement
        best = pack(order, tuple(i for i in best if i != removed) + (a, b))
    heuristic_reviews = len(active) - len(best)
    if pricing_rounds:
        original_directions = [tuple(int(j in pool) for j in range(m)) for pool in pools]
        pricing_needed = root_upper > len(best)
        proposals = (price_directions(list(columns.values()), capacity, original_directions,
                                      pricing_rounds, len(best)) if pricing_needed else [])
        for weights in proposals:
            candidate = pack(sorted(active, key=lambda i: (
                sum(a * p for a, p in zip(columns[i], weights)), max(columns[i]), i)))
            if len(candidate) > len(best):
                best = candidate
            priced_surrogates.append((weights, sorted((sum(a * p for a, p in zip(column, weights)),
                                                      g, len(ids)) for g, (column, ids) in enumerate(groups))))
        priced_surrogates = sorted(priced_surrogates, key=lambda pair:
                                   scalar_bound(list(columns.values()), capacity, pair[0])[0])[:6]
        root_upper = upper_bound(0, caps, 0)
        prices = [F(0)] * len(rows)
        if original_directions:
            _, direction = min((scalar_bound(list(columns.values()), capacity, d)[0], d)
                               for d in original_directions + proposals)
            _, _, pivot = scalar_bound(list(columns.values()), capacity, direction)
            for j, weight in enumerate(direction):
                prices[matrix.index(tight[j])] = F(scale * weight, pivot)
        dual_info = {"pricing_rounds": pricing_rounds, "pricing_skipped": not pricing_needed,
                     "search_directions": len(priced_surrogates),
                     "proposed_directions": len(proposals),
                     "pricing_reviews": len(active) - len(best), "target_prices": [str(p) for p in prices]}
    stack = [(root_upper, 0, caps, ())] if root_upper > len(best) else []
    nodes = 0
    while stack and nodes < node_budget:
        inherited, pos, remaining, kept = stack.pop()
        nodes += 1
        if inherited <= len(best):
            continue
        if len(kept) > len(best):
            best = tuple(sorted(kept))
        upper = upper_bound(pos, remaining, len(kept))
        if upper <= len(best):
            continue
        column, ids = groups[pos]
        maximum = min(len(ids), *(remaining[j] // v for j, v in enumerate(column) if v))
        for take in range(maximum + 1):
            if len(kept) + take + suffix[pos + 1] > len(best):
                child_caps = tuple(a - take * b for a, b in zip(remaining, column))
                stack.append((upper, pos + 1, child_caps, kept + ids[:take]))
    frontier_upper = max([len(best)] + [bound for bound, _, _, _ in stack])
    chosen = tuple(i for i in active if i not in best)
    diagnostics = {"algorithm": "integer_surrogate_grouped/v1", "node_budget": node_budget,
                   "exchange_budget": exchange_budget, "exchange_checks": checks,
                   "portfolio_reviews": portfolio_reviews, "heuristic_reviews": heuristic_reviews,
                   "nodes_visited": nodes, "contribution_groups": len(groups),
                   "binding_targets": m, "integer_scale_bits": scale.bit_length(),
                   "root_lower_bound": len(active) - root_upper,
                   "budget_exhausted": bool(stack) and nodes == node_budget,
                   "search_proved_optimal": frontier_upper == len(best)}
    if pricing_rounds:
        diagnostics["dual"] = dual_info
    return chosen, len(active) - frontier_upper, diagnostics
