# SPDX-License-Identifier: MIT
"""Independent subset checks and optimization-free proof verification."""
from copy import deepcopy
from fractions import Fraction as F
import random

import pytest

from robustband.review import ReviewProblem, Target
from robustband.review_dual import price_directions, scalar_bound
from test_review_search import optimum


def test_shared_prices_against_all_subsets_at_several_budgets():
    rng = random.Random(20261014)
    for case in range(60):
        n = 8
        raw = [[rng.randrange(0, 9) for _ in range(n)] for _ in range(3)]
        intervals = tuple(rng.choice(((-1, 1), (-1, 0), (0, 1), (0, 0))) for _ in range(n))
        p = ReviewProblem(tuple(str(i) for i in range(n)), intervals,
                          tuple(Target(str(j), tuple(F(v, sum(row)) for v in row))
                                for j, row in enumerate(raw)))
        reviewed = {"0": intervals[0][0]} if case % 3 == 0 else {}
        epsilon = rng.choice((F(0), F(1, 3), F(1, 2), F(1), F(2)))
        best = optimum(p, epsilon, reviewed)
        for budget in (0, 1, 10000):
            previous = p.plan_optimized(epsilon, reviewed, node_budget=budget, exchange_budget=100)
            plan = p.plan_refined(epsilon, reviewed, node_budget=budget, exchange_budget=100, pricing_rounds=2)
            cert = plan["lower_bound_certificate"]
            assert p.verify_lower_bound(cert)
            assert cert["query_lower_bound"] <= best <= plan["n_reviews"] <= previous["n_reviews"]
            assert plan["query_lower_bound"] <= best
            selected = set(plan["selected_ids"])
            assert selected.isdisjoint(reviewed)
            widths = {t.name: sum(w * (hi - lo) for name, w, (lo, hi) in zip(
                p.item_ids, t.weights, intervals) if name not in selected and name not in reviewed)
                      for t in p.targets}
            assert widths == {k: F(v) for k, v in plan["residual_widths"].items()}
            assert max(widths.values()) <= epsilon and plan["width_guaranteed"]
            if plan["optimality"] == "MINIMUM_CARDINALITY":
                assert plan["n_reviews"] == best
            if budget == 10000:
                assert plan["n_reviews"] == best


def test_exact_certificate_rejects_changes_without_calling_optimizer(monkeypatch):
    p = ReviewProblem(("a", "b", "c", "d"), ((-1, 1),) * 4, (
        Target("left", (F(1, 2), F(1, 2), 0, 0)),
        Target("right", (0, 0, F(1, 2), F(1, 2)))))
    cert = p.plan_refined(1)["lower_bound_certificate"]
    assert cert["query_lower_bound"] == 2
    def fail(*args, **kwargs):
        raise AssertionError("a standalone verifier must not run an optimizer")
    monkeypatch.setattr("robustband.review.optimize_widths", fail)
    assert p.verify_lower_bound(cert)
    for field, value in (("query_lower_bound", 3), ("retained_upper_bound", "1"),
                         ("problem_digest", "invalid"), ("epsilon", "0")):
        modified = deepcopy(cert)
        modified[field] = value
        assert not p.verify_lower_bound(modified)
    bad = deepcopy(cert)
    bad["target_prices"]["left"] = "-1"
    assert not p.verify_lower_bound(bad)
    assert not p.verify_lower_bound({})
    assert not p.verify_lower_bound({"epsilon": 0, "target_prices": None, "reviewed": {}})


def test_bad_guidance_cannot_invalidate_exact_bounds(monkeypatch):
    raw = [[5, 7, 6, 1, 9, 9, 9, 1, 7], [5, 6, 6, 6, 8, 2, 4, 6, 6],
           [2, 1, 9, 7, 2, 9, 5, 6, 1]]
    p = ReviewProblem(tuple(str(i) for i in range(9)), ((-1, 1),) * 9,
                      tuple(Target(str(j), tuple(F(v, sum(row)) for v in row))
                            for j, row in enumerate(raw)))
    monkeypatch.setattr("robustband.review_search.price_directions", lambda *args: [(1000000, 0, 1)])
    plan = p.plan_refined(F(2, 3), node_budget=0, exchange_budget=0)
    assert p.verify_lower_bound(plan["lower_bound_certificate"])
    assert plan["lower_bound_certificate"]["query_lower_bound"] <= optimum(p, F(2, 3), {})
    assert plan["width_guaranteed"]


def test_certificate_is_invariant_to_zero_effect_items_and_duplicate_targets():
    weights = (F(1, 2), F(1, 3), F(1, 6))
    p = ReviewProblem(("a", "b", "c"), ((-1, 1),) * 3, (Target("t", weights),))
    baseline = p.lower_bound_certificate("1/3", {"t": 3})
    augmented = ReviewProblem(("a", "b", "c", "free"), ((-1, 1),) * 4,
                              (Target("t", weights + (0,)), Target("copy", weights + (0,))))
    cert = augmented.lower_bound_certificate("1/3", {"t": 3, "copy": 0})
    assert cert["query_lower_bound"] == baseline["query_lower_bound"] == 2
    assert F(cert["retained_upper_bound"]) == F(baseline["retained_upper_bound"]) + 1
    assert p.plan_refined("1/3")["lower_bound_certificate"]["query_lower_bound"] == 2
    assert p.plan_refined(2)["n_reviews"] == 0
    assert p.plan_refined(0, {"a": 0})["n_reviews"] == 2
    assert p.plan_refined(0, pricing_rounds=0)["width_guaranteed"]


def test_scalar_and_hinge_guidance_boundary_cases():
    assert scalar_bound([(0,), (1,)], 1, (1,)) == (F(2), 2, 0)
    assert price_directions([], 1, [], 2, 0) == []
    assert price_directions([(1, 1)], 0, [(1, 1)], 2, 0) == []
    assert price_directions([(1,)], 1, [(1,)], 2, 0) == []
    # Exact capacity saturates below the hinge: its subgradient has zero norm.
    assert price_directions([(1, 1), (1, 1), (2, 2)], 2,
                            [(1, 0), (0, 1), (1, 1)], 2, 2)
    huge = 10 ** 1000
    directions = price_directions([(huge, 1), (1, huge), (huge // 2, huge // 2)],
                                  huge // 2, [(1, 0), (0, 1), (1, 1)], 2, 0)
    assert directions and all(all(isinstance(v, int) and v >= 0 for v in d) for d in directions)


def test_validation_and_conflict_do_not_turn_into_optimization_claims():
    p = ReviewProblem(("a", "b"), ((1, 1), (-1, -1)), (Target("p", (1, 0)), Target("n", (0, 1))))
    assert p.plan_refined(0)["optimality"] == "NOT_APPLICABLE"
    for epsilon, budget, rounds in ((-1, 1, 1), (0, -1, 1), (0, 1, -1), (0, 1, True)):
        with pytest.raises(ValueError):
            p.plan_refined(epsilon, node_budget=budget, pricing_rounds=rounds)
    for epsilon, prices in ((-1, {"p": 0, "n": 0}), (0, {"p": 0}), (0, {"p": -1, "n": 1})):
        with pytest.raises(ValueError):
            p.lower_bound_certificate(epsilon, prices)
    with pytest.raises(ValueError):
        p.plan_refined(0, {"a": -1})


def test_shared_prices_reduce_reviews_without_search():
    raw = [[7, 4, 10, 1, 10, 5, 7, 7, 2, 1], [4, 11, 6, 1, 4, 5, 6, 12, 5, 5],
           [9, 1, 3, 2, 12, 10, 10, 2, 8, 12]]
    p = ReviewProblem(tuple(str(i) for i in range(10)), ((-1, 1),) * 10,
                      tuple(Target(str(j), tuple(F(v, sum(row)) for v in row))
                            for j, row in enumerate(raw)))
    epsilon = F(2, 3)
    old = p.plan_optimized(epsilon, node_budget=0, exchange_budget=0)
    new = p.plan_refined(epsilon, node_budget=0, exchange_budget=0, pricing_rounds=2)
    assert old["n_reviews"] == 7
    assert new["n_reviews"] == optimum(p, epsilon, {}) == 6
    assert new["search"]["nodes_visited"] == 0
    assert new["lower_bound_certificate"]["query_lower_bound"] == 6
