# SPDX-License-Identifier: MIT
"""Independent completion/subset oracles for the experimental review planner."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import combinations, product
import random

import pytest

from robustband.review import ReviewProblem, Target, from_predictions, linear_target


def problem(intervals, weights=((F(1, 3),) * 3,)):
    return ReviewProblem(tuple("q%d" % i for i in range(len(intervals))), intervals,
                         tuple(Target("t%d" % j, w) for j, w in enumerate(weights)))


def test_bounds_and_decisions_against_every_completion():
    p = problem(((-1, 0), (0, 1), (-1, 1)), ((F(1, 2), F(1, 3), F(1, 6)),))
    for observed in ({}, {"q0": 0}, {"q0": 0, "q1": 1}, {"q0": -1, "q1": 0, "q2": 0}):
        worlds = [v for v in product((-1, 0), (0, 1), (-1, 0, 1))
                  if all(v[int(k[1:])] == value for k, value in observed.items())]
        margins = [sum(w * value for w, value in zip(p.targets[0].weights, v)) for v in worlds]
        assert p.bounds(observed)["t0"] == (min(margins), max(margins))
        if p.status(observed) == "ROBUST":
            assert all(m > 0 for m in margins)
        if p.status(observed) == "REFUTED":
            assert all(m <= 0 for m in margins)


def test_target_conflict_is_not_fixed_by_more_labels():
    p = problem(((1, 1), (-1, -1), (-1, 1)),
                ((F(3, 4), F(1, 4), 0), (F(1, 4), F(3, 4), 0)))
    assert p.status() == "TARGET_CONFLICT"
    for d in (-1, 0, 1):
        assert p.status({"q2": d}) == "TARGET_CONFLICT"
    plan = p.plan(0)
    assert plan["selected_ids"] == [] and plan["method"] == "choose_target"
    assert plan["optimality"] == "NOT_APPLICABLE"


def test_plan_minimum_by_independent_subset_oracle():
    rng = random.Random(20261012)
    for _ in range(30):
        n = 6
        intervals = tuple(rng.choice(((-1, 1), (0, 1), (0, 0))) for _ in range(n))
        raw = [[rng.randrange(1, 10) for _ in range(n)] for _ in range(3)]
        weights = tuple(tuple(F(v, sum(row)) for v in row) for row in raw)
        p = problem(intervals, weights)
        epsilon = F(1, 4)
        sizes = [len(s) for k in range(n + 1) for s in combinations(range(n), k) if all(
            sum(w * (hi - lo) for i, (w, (lo, hi)) in enumerate(zip(t.weights, intervals))
                if i not in s) <= epsilon for t in p.targets)]
        plan = p.plan(epsilon, exact_limit=6)
        assert plan["n_reviews"] == min(sizes)
        assert plan["query_lower_bound"] == min(sizes)
        assert plan["optimality"] == "MINIMUM_CARDINALITY"
        assert plan["width_guaranteed"]


def test_plan_after_reviews_and_single_target_optimum():
    p = problem(((-1, 1), (-1, 1), (0, 1)), ((F(1, 2), F(1, 3), F(1, 6)),))
    plan = p.plan("1/6", {"q0": 0})
    assert plan["selected_ids"] == ["q1"]
    assert plan["reviewed_ids"] == ["q0"]
    assert plan["method"] == "sorted_width"
    assert p.plan(2)["n_reviews"] == 0
    assert p.plan(0)["n_reviews"] == 3


def test_large_plan_exposes_lower_bound_instead_of_false_optimality():
    p = problem(((-1, 1),) * 4,
                ((F(1, 2), F(1, 2), 0, 0), (0, 0, F(1, 2), F(1, 2))))
    plan = p.plan(1, exact_limit=0)
    assert plan["n_reviews"] == 2
    assert plan["query_lower_bound"] == 1
    assert plan["optimality"] == "FEASIBLE_WITH_LOWER_BOUND"
    assert p.plan(1, exact_limit=4)["optimality"] == "MINIMUM_CARDINALITY"


def test_certificates_detect_modification_and_out_of_domain_review():
    p = problem(((-1, 1), (0, 1), (0, 0)))
    cert = p.certificate({"q0": 0})
    assert p.verify_certificate(cert)
    bad = deepcopy(cert)
    bad["target_bounds"]["t0"][0] = "1"
    assert not p.verify_certificate(bad)
    assert not p.verify_certificate({})
    bad = deepcopy(cert)
    bad["reviewed"] = {"q2": "1"}
    assert not p.verify_certificate(bad)
    with pytest.raises(ValueError, match="outside"):
        p.bounds({"q2": 1})
    with pytest.raises(ValueError, match="unknown"):
        p.bounds({"missing": 0})


@pytest.mark.parametrize("agg,expected", [
    ("micro", (F(1, 3),) * 3),
    ("macro_class", (F(1, 4), F(1, 4), F(1, 2))),
    ("macro_len", (F(1, 2), F(1, 4), F(1, 4))),
])
def test_targets_keep_full_record_denominators(agg, expected):
    metas = [{"class": "a", "len_bucket": 0}, {"class": "a", "len_bucket": 1},
             {"class": "b", "len_bucket": 1}]
    assert linear_target(metas, agg).weights == expected
    assert linear_target([{}, {}], "macro_class").weights == (F(1, 2),) * 2


def test_prediction_domains_are_opt_in_and_bound_to_input():
    preds = {"a": {"items": [("42 no wait 7", "42", {})]},
             "b": {"items": [("7", "42", {})]}}
    pairs = [("strict_exact", "exact_match"), ("first_num", "exact_match")]
    safe = from_predictions(preds, "a", "b", pairs)
    conditional = from_predictions(preds, "a", "b", pairs, domain="candidate", item_ids=["test-id"])
    assert safe.intervals == ((F(-1), F(1)),)
    assert conditional.intervals == ((F(0), F(1)),)
    assert safe.fingerprint() != conditional.fingerprint()
    assert "not validated" in conditional.assumptions[-1]
    assert conditional.status({"test-id": 1}) == "ROBUST"
    with pytest.raises(ValueError, match="outside"):
        conditional.status({"test-id": -1})


@pytest.mark.parametrize("change", ["length", "gold", "domain", "measurements", "parser"])
def test_prediction_factory_rejects_invalid_scope(change):
    preds = {"a": {"items": [("1", "1", {})]}, "b": {"items": [("1", "1", {})]}}
    kw = {"measurements": [("last_num", "exact_match")]}
    if change == "length":
        preds["b"]["items"] = []
    elif change == "gold":
        preds["b"]["items"] = [("1", "2", {})]
    elif change == "domain":
        kw["domain"] = "guess"
    elif change == "measurements":
        kw["measurements"] = []
    else:
        kw["measurements"] = [("missing", "exact_match")]
    with pytest.raises(ValueError):
        from_predictions(preds, "a", "b", **kw)


@pytest.mark.parametrize("ids,intervals,targets", [
    ((), (), (Target("t", (1,)),)),
    (("q", "q"), ((0, 0),) * 2, (Target("t", (F(1, 2),) * 2),)),
    (("q",), ((1, -1),), (Target("t", (1,)),)),
    (("q",), ((0, 0),), ()),
    (("q",), ((0, 0),), (Target("t", (1,)), Target("t", (1,)))),
    (("q",), ((0, 0),), (Target("t", (F(1, 2),) * 2),)),
])
def test_invalid_problem(ids, intervals, targets):
    with pytest.raises(ValueError):
        ReviewProblem(ids, intervals, targets)


def test_invalid_target_and_plan_and_nonlinear_aggregation():
    for name, weights in (("", (1,)), ("bad", (-1, 2)), ("bad", (0,))):
        with pytest.raises(ValueError):
            Target(name, weights)
    for metas, agg in (([], "micro"), ([{}], "median")):
        with pytest.raises(ValueError):
            linear_target(metas, agg)
    p = problem(((-1, 1),) * 3)
    for epsilon, exact_limit in ((-1, 1), (0, -1), (0, 21), (0, 0.5)):
        with pytest.raises(ValueError):
            p.plan(epsilon, exact_limit=exact_limit)
