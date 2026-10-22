# SPDX-License-Identifier: MIT
"""Hinge dual guidance and exact, independently checkable review lower bounds.

Floating point proposes shared target prices. Only nonnegative integer prices
enter packing/search; Fraction arithmetic certifies the resulting bound. The
guidance can be inaccurate without invalidating a certificate.
"""
from fractions import Fraction as F
from math import gcd


def scalar_bound(columns, capacity, direction):
    """Exact fractional scalar relaxation, retained count and next cost."""
    costs = sorted(sum(a * p for a, p in zip(col, direction)) for col in columns)
    remaining = capacity * sum(direction)
    for count, cost in enumerate(costs):
        if cost > remaining:
            return F(count) + F(remaining, cost), count, cost
        remaining -= cost
    return F(len(costs)), len(costs), 0


def price_directions(columns, capacity, directions, rounds, feasible_count):
    """Coordinate-minimize a clipped hinge surrogate to propose price vectors.

    The clipping and floating thresholds guide proposals only. The actual
    constraint coefficients are never clipped when verifying or searching.
    Coordinate descent on a nonsmooth convex function need not reach its global
    minimum. Keep all original directions and treat every proposal as optional.
    """
    if not columns or capacity == 0 or len(columns[0]) < 2:
        return []
    m = len(columns[0])
    ranked = sorted((scalar_bound(columns, capacity, d)[0], d) for d in directions)
    initial = [d for _, d in ranked[:2]]
    normalized = [tuple(float(F(min(col[j], capacity), capacity)) for col in columns)
                  for j in range(m)]
    proposals = []
    def record(prices):
        maximum = max(prices)
        if maximum > 0:
            integers = tuple(round(4096 * (p / maximum)) for p in prices)
            divisor = gcd(*integers)
            proposals.append(tuple(p // divisor for p in integers))

    for direction in initial:
        _, _, pivot = scalar_bound(columns, capacity, direction)
        prices = [float(F(p * capacity, pivot)) for p in direction]
        for _ in range(rounds):
            for j in range(m):
                knots = []
                for i, col in enumerate(columns):
                    b = 1 - sum(prices[k] * normalized[k][i] for k in range(m) if k != j)
                    if b > 0 and normalized[j][i] > 0:
                        knots.append((b / normalized[j][i], min(col[j], capacity)))
                slope_mass = sum(a for _, a in knots)
                price = 0.0
                for knot, mass in sorted(knots):
                    if slope_mass <= capacity:
                        break
                    price = knot
                    slope_mass -= mass
                prices[j] = price
            record(prices)
        # Coordinate descent can stop at a nonglobal nonsmooth minimum.
        # Shared projected subgradients allow simultaneous price adjustments.
        for step_number in range(16 * rounds):
            scores = [sum(prices[j] * normalized[j][i] for j in range(m)) for i in range(len(columns))]
            active = [i for i, s in enumerate(scores) if s < 1]
            gradient = [1 - sum(normalized[j][i] for i in active) for j in range(m)]
            norm = sum(g * g for g in gradient)
            if norm == 0:
                break
            objective = sum(prices) + sum(max(0.0, 1 - s) for s in scores)
            step = 0.75 * max(0.0, objective - feasible_count) / norm
            prices = [min(len(columns), max(0.0, p - step * g)) for p, g in zip(prices, gradient)]
            if step_number % 8 == 0:
                record(prices)
    return list(dict.fromkeys(proposals))


def hinge_bound(rows, epsilon, prices):
    """Weak-duality bound for any nonnegative rational target prices.

    sum(x_i) <= epsilon*sum(prices) + sum(max(0,1-price dot contribution_i))
    for any feasible retained-item vector x in {0,1}^n. No optimizer is called.
    """
    costs = [sum(p * row[i] for p, row in zip(prices, rows)) for i in range(len(rows[0]))]
    return epsilon * sum(prices) + sum(max(F(0), 1 - c) for c in costs)
