# SPDX-License-Identifier: MIT
"""Exhaustive rational oracle for optimized plans and honest cutoff bounds."""
from fractions import Fraction as F
from itertools import combinations
import random

import pytest

from robustband.review import ReviewProblem, Target


def optimum(problem, epsilon, reviewed):
    candidates = [i for i, name in enumerate(problem.item_ids) if name not in reviewed]
    for k in range(len(candidates) + 1):
        for selected in combinations(candidates, k):
            if all(sum(w * (hi - lo) for i, (w, (lo, hi)) in enumerate(
                    zip(t.weights, problem.intervals)) if i not in selected
                    and problem.item_ids[i] not in reviewed) <= epsilon for t in problem.targets):
                return k


def test_optimized_against_independent_all_subsets_with_budget_cutoffs():
    rng = random.Random(20261013)
    saw_search = saw_cutoff = saw_improvement = False
    for case in range(100):
        n = 8
        raw = [[rng.randrange(0, 8) for _ in range(n)] for _ in range(3)]
        targets = tuple(Target(str(j), tuple(F(v, sum(row)) for v in row))
                        for j, row in enumerate(raw))
        intervals = tuple(rng.choice(((-1, 1), (0, 1), (-1, 0), (0, 0))) for _ in range(n))
        p = ReviewProblem(tuple(str(i) for i in range(n)), intervals, targets)
        reviewed = {"0": intervals[0][0]} if case % 3 == 0 else {}
        epsilon = rng.choice((F(0), F(1, 7), F(1, 2), F(1)))
        best = optimum(p, epsilon, reviewed)
        legacy = p.plan(epsilon, reviewed, exact_limit=0)
        for budget in (0, 1, 10000):
            plan = p.plan_optimized(epsilon, reviewed, node_budget=budget)
            ids = set(plan["selected_ids"])
            assert ids.isdisjoint(reviewed)
            residual = {t.name: sum(w * (hi - lo) for name, w, (lo, hi) in zip(
                p.item_ids, t.weights, intervals) if name not in ids and name not in reviewed)
                        for t in targets}
            assert residual == {k: F(v) for k, v in plan["residual_widths"].items()}
            assert max(residual.values()) <= epsilon and plan["width_guaranteed"]
            assert plan["query_lower_bound"] <= best <= plan["n_reviews"] <= legacy["n_reviews"]
            assert plan["optimality_gap"] == plan["n_reviews"] - plan["query_lower_bound"]
            assert plan["search"]["nodes_visited"] <= budget
            if plan["optimality"] == "MINIMUM_CARDINALITY":
                assert plan["n_reviews"] == best
            if budget == 10000:
                assert plan["optimality"] == "MINIMUM_CARDINALITY"
            saw_search |= bool(plan["search"]["nodes_visited"])
            saw_cutoff |= plan["search"]["budget_exhausted"]
            saw_improvement |= plan["n_reviews"] < legacy["n_reviews"]
    assert saw_search and saw_cutoff and saw_improvement


def test_surrogate_bound_proves_large_disjoint_targets_without_search():
    n = 120
    p = ReviewProblem(tuple(str(i) for i in range(n)), ((-1, 1),) * n, (
        Target("left", (F(1, 60),) * 60 + (0,) * 60),
        Target("right", (0,) * 60 + (F(1, 60),) * 60)))
    legacy = p.plan(1, exact_limit=0)
    plan = p.plan_optimized(1, node_budget=0)
    assert legacy["query_lower_bound"] == 30
    assert plan["n_reviews"] == plan["query_lower_bound"] == 60
    assert plan["search"]["nodes_visited"] == 0
    assert plan["search"]["contribution_groups"] == 2
    assert plan["optimality"] == "MINIMUM_CARDINALITY"


def test_duplicates_dominance_and_nonbinding_rows_do_not_change_constraints():
    p = ReviewProblem(("a", "b", "c", "d"), ((-1, 1), (-1, 1), (0, 0), (0, 0)), (
        Target("binding", (F(1, 2), F(1, 2), 0, 0)),
        Target("duplicate", (F(1, 2), F(1, 2), 0, 0)),
        Target("weaker", (F(1, 4), F(1, 4), F(1, 2), 0)),
        Target("nonbinding", (0, 0, 0, 1))))
    plan = p.plan_optimized(F(3, 4))
    assert plan["search"]["binding_targets"] == 1
    assert plan["n_reviews"] == 2
    assert p.plan_optimized(2)["n_reviews"] == 0
    assert p.plan_optimized(0, {"a": 0, "b": 0})["n_reviews"] == 0


def test_arbitrary_precision_threshold_is_never_rounded_to_feasible():
    huge = 10 ** 50
    p = ReviewProblem(("a", "b"), ((0, 1), (0, 1)), (
        Target("t", (F(huge + 1, 2 * huge), F(huge - 1, 2 * huge))),))
    plan = p.plan_optimized(F(1, 2))
    assert plan["selected_ids"] == ["a"]
    assert F(plan["residual_widths"]["t"]) < F(1, 2)


def test_conflict_and_validation_remain_explicit():
    p = ReviewProblem(("a", "b"), ((1, 1), (-1, -1)), (
        Target("positive", (1, 0)), Target("negative", (0, 1))))
    plan = p.plan_optimized(0)
    assert plan["method"] == "choose_target" and plan["optimality"] == "NOT_APPLICABLE"
    for epsilon, budget in ((-1, 1), (0, -1), (0, 1.2), (0, True)):
        with pytest.raises(ValueError):
            p.plan_optimized(epsilon, node_budget=budget)
    with pytest.raises(ValueError, match="outside"):
        p.plan_optimized(0, {"a": -1})


def test_many_targets_use_bounded_surrogate_portfolio():
    rng = random.Random(19)
    raw = [[rng.randrange(1, 10) for _ in range(6)] for _ in range(12)]
    targets = tuple(Target(str(j), tuple(F(v, sum(row)) for v in row))
                    for j, row in enumerate(raw))
    p = ReviewProblem(tuple(str(i) for i in range(6)), ((-1, 1),) * 6, targets)
    assert p.plan_optimized(1)["search"]["binding_targets"] == 12
    assert p.plan_optimized(1)["n_reviews"] == optimum(p, F(1), {})


def test_grouped_search_matches_independent_oracle():
    rng = random.Random(39)
    for _ in range(20):
        raw = [[v for v in [rng.randrange(1, 9) for _ in range(4)] for _ in range(2)]
               for _ in range(3)]
        p = ReviewProblem(tuple(str(i) for i in range(8)), ((-1, 1),) * 8,
                          tuple(Target(str(j), tuple(F(v, sum(row)) for v in row))
                                for j, row in enumerate(raw)))
        plan = p.plan_optimized(F(5, 6))
        assert plan["search"]["contribution_groups"] <= 4
        assert plan["n_reviews"] == optimum(p, F(5, 6), {})
        assert plan["optimality"] == "MINIMUM_CARDINALITY"


def test_search_improves_incumbent_and_exchange_can_replace_two_reviews():
    raw = [[5, 7, 6, 1, 9, 9, 9, 1, 7], [5, 6, 6, 6, 8, 2, 4, 6, 6],
           [2, 1, 9, 7, 2, 9, 5, 6, 1]]
    p = ReviewProblem(tuple(str(i) for i in range(9)), ((-1, 1),) * 9,
                      tuple(Target(str(j), tuple(F(v, sum(row)) for v in row))
                            for j, row in enumerate(raw)))
    epsilon = F(2, 3)
    portfolio = p.plan_optimized(epsilon, node_budget=0, exchange_budget=0)
    searched = p.plan_optimized(epsilon, exchange_budget=0)
    exchanged = p.plan_optimized(epsilon, node_budget=0)
    assert portfolio["n_reviews"] == 7
    assert searched["n_reviews"] == exchanged["n_reviews"] == optimum(p, epsilon, {}) == 6
    assert searched["search"]["nodes_visited"] > 0
    assert exchanged["search"]["exchange_checks"] > 0
    assert p.plan_optimized(epsilon, node_budget=0, exchange_budget=1)["width_guaranteed"]
    with pytest.raises(ValueError):
        p.plan_optimized(epsilon, exchange_budget=-1)
