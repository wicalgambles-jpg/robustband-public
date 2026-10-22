# SPDX-License-Identifier: MIT
"""Experimental, finite-record review planning for declared linear targets.

Bounds range over independent per-item completions, not the original global
protocol family and not a statistical population confidence interval. Reviews
must be trusted and lie inside the declared item domains. Candidate-derived
domains therefore require an explicit coverage assumption.
"""
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction as F
from hashlib import sha256
from itertools import combinations
import json

from .metrics import METRIC
from .parsers import PARSE
from .review_search import optimize_widths
from .review_dual import hinge_bound


def _f(value):
    return F(str(value))


@dataclass(frozen=True)
class Target:
    """A fixed nonnegative weight vector, summing to one on the full record."""
    name: str
    weights: tuple

    def __post_init__(self):
        object.__setattr__(self, "weights", tuple(_f(x) for x in self.weights))
        if not self.name or any(x < 0 for x in self.weights) or sum(self.weights) != 1:
            raise ValueError("targets need a name and nonnegative weights summing to one")


def linear_target(metas, agg):
    """Encode micro/macro as full-record weights; reject nonlinear aggregators."""
    n = len(metas)
    if not n:
        raise ValueError("targets require a nonempty record")
    if agg == "micro":
        return Target(agg, (F(1, n),) * n)
    keys = {"macro_class": "class", "macro_len": "len_bucket"}
    if agg not in keys:
        raise ValueError("review planning supports micro, macro_class and macro_len only")
    groups = [(m or {}).get(keys[agg]) for m in metas]
    counts = Counter(groups)
    return Target(agg, tuple(F(1, len(counts) * counts[g]) for g in groups))


@dataclass(frozen=True)
class ReviewProblem:
    """Paired-score difference intervals and fixed evaluation targets.

    Each interval bounds a trusted difference in [-1,1]. Once a review is
    revealed, its value replaces that interval without changing denominators.
    No response is assumed during planning. Review costs are one per item.
    """
    item_ids: tuple
    intervals: tuple
    targets: tuple
    assumptions: tuple = ("trusted reviews lie inside the declared intervals",)
    input_digest: str = ""
    threshold: F = F(0)

    def __post_init__(self):
        object.__setattr__(self, "item_ids", tuple(self.item_ids))
        object.__setattr__(self, "intervals", tuple((_f(lo), _f(hi)) for lo, hi in self.intervals))
        object.__setattr__(self, "targets", tuple(self.targets))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "threshold", _f(self.threshold))
        n = len(self.item_ids)
        if not n or len(set(self.item_ids)) != n or any(not isinstance(i, str) or not i for i in self.item_ids):
            raise ValueError("item IDs must be unique nonempty strings")
        if len(self.intervals) != n or any(not (-1 <= lo <= hi <= 1) for lo, hi in self.intervals):
            raise ValueError("one ordered difference interval in [-1,1] is required per item")
        if not self.targets or len({t.name for t in self.targets}) != len(self.targets):
            raise ValueError("provide at least one uniquely named target")
        if any(len(t.weights) != n for t in self.targets):
            raise ValueError("target weights must match the full item record")

    def _reviews(self, reviewed):
        values = {k: _f(v) for k, v in (reviewed or {}).items()}
        domains = dict(zip(self.item_ids, self.intervals))
        for key, value in values.items():
            if key not in domains or not domains[key][0] <= value <= domains[key][1]:
                raise ValueError("unknown item or review outside its domain; revise assumptions and restart")
        return values

    def bounds(self, reviewed=None):
        """Exact extremal margins over all remaining independent completions."""
        values = self._reviews(reviewed)
        domains = [(values[i], values[i]) if i in values else d
                   for i, d in zip(self.item_ids, self.intervals)]
        return {t.name: (sum(w * d[0] for w, d in zip(t.weights, domains)),
                         sum(w * d[1] for w, d in zip(t.weights, domains))) for t in self.targets}

    def status(self, reviewed=None):
        """TARGET_CONFLICT means no in-domain review can reconcile all targets."""
        bounds = list(self.bounds(reviewed).values())
        positive = any(lo > self.threshold for lo, _ in bounds)
        nonpositive = any(hi <= self.threshold for _, hi in bounds)
        if positive and nonpositive:
            return "TARGET_CONFLICT"
        if all(lo > self.threshold for lo, _ in bounds):
            return "ROBUST"
        if all(hi <= self.threshold for _, hi in bounds):
            return "REFUTED"
        return "NEEDS_REVIEW"

    def fingerprint(self):
        """Bind targets, domains, assumptions and any raw-input digest."""
        payload = {"ids": self.item_ids, "intervals": [[str(a), str(b)] for a, b in self.intervals],
                   "targets": [(t.name, [str(w) for w in t.weights]) for t in self.targets],
                   "threshold": str(self.threshold), "assumptions": self.assumptions,
                   "input_digest": self.input_digest}
        return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def certificate(self, reviewed=None):
        """Reproducible bounds; no claim that a reviewer or a domain is correct."""
        values = self._reviews(reviewed)
        return {"schema": "robustband.review_certificate/v1", "problem_digest": self.fingerprint(),
                "assumptions": list(self.assumptions), "threshold": str(self.threshold),
                "reviewed": {k: str(values[k]) for k in self.item_ids if k in values},
                "target_bounds": {k: [str(lo), str(hi)] for k, (lo, hi) in self.bounds(values).items()},
                "status": self.status(values)}

    def verify_certificate(self, cert):
        """Reject modified bounds, reviews, assumptions or problem identity."""
        try:
            return cert == self.certificate(cert["reviewed"])
        except (KeyError, ValueError, TypeError):
            return False

    def plan(self, epsilon, reviewed=None, exact_limit=16):
        """Review set guaranteeing width <= epsilon for every target.

        Single-target plans are optimal by sorting weighted interval widths.
        Small multi-target plans use exact subset search. Larger plans use
        minimax greedy and expose a lower bound; they never claim optimality
        unless that bound matches. Width precision does not guarantee a sign.
        """
        epsilon = _f(epsilon)
        if epsilon < 0 or not isinstance(exact_limit, int) or not 0 <= exact_limit <= 20:
            raise ValueError("epsilon must be nonnegative and exact_limit an integer in [0,20]")
        values = self._reviews(reviewed)
        contributions = [tuple(F(0) if i in values else w * (hi - lo)
                               for i, (lo, hi), w in zip(self.item_ids, self.intervals, t.weights))
                         for t in self.targets]
        residual = [sum(row) for row in contributions]
        if self.status(values) == "TARGET_CONFLICT":
            return self._plan_result((), residual, epsilon, 0, "NOT_APPLICABLE", "choose_target", values)
        active = [i for i in range(len(self.item_ids)) if any(row[i] > 0 for row in contributions)]
        lower = 0
        for row, width in zip(contributions, residual):
            k = 0
            for value in sorted(row, reverse=True):
                if width <= epsilon:
                    break
                width -= value
                k += 1
            lower = max(lower, k)
        chosen = []
        left = set(active)
        while max(residual) > epsilon:
            current = max(residual)
            key = lambda i: (current - max(r - row[i] for r, row in zip(residual, contributions)),
                             sum(row[i] for row in contributions), -i)
            pick = max(left, key=key)
            chosen.append(pick)
            left.remove(pick)
            residual = [r - row[pick] for r, row in zip(residual, contributions)]
        optimal = len(chosen) == lower
        method = "sorted_width" if len(self.targets) == 1 else "minimax_greedy"
        if not optimal and len(active) <= exact_limit:
            for k in range(lower, len(chosen)):
                solution = next((q for q in combinations(active, k) if all(
                    sum(row) - sum(row[i] for i in q) <= epsilon for row in contributions)), None)
                if solution is not None:
                    chosen = list(solution)
                    break
            optimal, lower, method = True, len(chosen), "exact_subset"
            residual = [sum(row) - sum(row[i] for i in chosen) for row in contributions]
        return self._plan_result(tuple(self.item_ids[i] for i in chosen), residual, epsilon, lower,
                                 "MINIMUM_CARDINALITY" if optimal else "FEASIBLE_WITH_LOWER_BOUND", method, values)

    def _plan_result(self, selected, residual, epsilon, lower, optimality, method, reviewed):
        return {"schema": "robustband.review_plan/v1", "problem_digest": self.fingerprint(),
                "reviewed_ids": [i for i in self.item_ids if i in reviewed], "selected_ids": list(selected),
                "n_reviews": len(selected), "epsilon": str(epsilon), "query_lower_bound": lower,
                "residual_widths": {t.name: str(w) for t, w in zip(self.targets, residual)},
                "width_guaranteed": all(w <= epsilon for w in residual),
                "optimality": optimality, "method": method}

    def plan_optimized(self, epsilon, reviewed=None, node_budget=5000, exchange_budget=20000):
        """Budgeted integer planner with a feasible incumbent and certified gap.

        Uses the same domains, unit costs and width objective as ``plan``.
        The retained-item complement admits surrogate capacity bounds and
        grouping of identical contribution vectors. A portfolio includes the
        legacy greedy set; cutoff exposes a valid lower bound, not a guessed
        optimum. ``node_budget=0`` runs the heuristic portfolio and root bounds.
        ``exchange_budget`` caps vector checks in one-for-two exchanges; zero
        disables exchanges. Budgets bound work rather than wall-clock time.
        """
        epsilon = _f(epsilon)
        if epsilon < 0 or any(isinstance(b, bool) or not isinstance(b, int) or b < 0
                              for b in (node_budget, exchange_budget)):
            raise ValueError("epsilon and integer search/exchange budgets must be nonnegative")
        values = self._reviews(reviewed)
        contributions = [tuple(F(0) if i in values else w * (hi - lo)
                               for i, (lo, hi), w in zip(self.item_ids, self.intervals, t.weights))
                         for t in self.targets]
        if self.status(values) == "TARGET_CONFLICT":
            return self._plan_result((), [sum(row) for row in contributions], epsilon, 0,
                                     "NOT_APPLICABLE", "choose_target", values)
        chosen, lower, diagnostics = optimize_widths(contributions, epsilon, node_budget, exchange_budget)
        residual = [sum(row) - sum(row[i] for i in chosen) for row in contributions]
        optimal = len(chosen) == lower
        result = self._plan_result(tuple(self.item_ids[i] for i in chosen), residual, epsilon, lower,
                                   "MINIMUM_CARDINALITY" if optimal else "FEASIBLE_WITH_LOWER_BOUND",
                                   "integer_surrogate_group_search", values)
        result["search"] = diagnostics
        result["optimality_gap"] = len(chosen) - lower
        return result

    def lower_bound_certificate(self, epsilon, prices, reviewed=None):
        """Standalone weak-duality proof of a necessary number of new reviews.

        Prices must map every target name to a nonnegative rational value. The
        certificate proves a finite-record width lower bound, not label accuracy.
        """
        epsilon = _f(epsilon)
        if epsilon < 0 or not isinstance(prices, dict) or set(prices) != {t.name for t in self.targets}:
            raise ValueError("declare nonnegative epsilon and a price for every target")
        prices = {name: _f(p) for name, p in prices.items()}
        if any(p < 0 for p in prices.values()):
            raise ValueError("dual prices must be nonnegative")
        values = self._reviews(reviewed)
        rows = [tuple(F(0) if i in values else w * (hi - lo)
                      for i, (lo, hi), w in zip(self.item_ids, self.intervals, t.weights))
                for t in self.targets]
        upper = hinge_bound(rows, epsilon, [prices[t.name] for t in self.targets])
        lower = len(self.item_ids) - min(len(self.item_ids), upper.numerator // upper.denominator)
        return {"schema": "robustband.review_lower_bound/v1", "problem_digest": self.fingerprint(),
                "epsilon": str(epsilon), "reviewed": {k: str(v) for k, v in values.items()},
                "target_prices": {t.name: str(prices[t.name]) for t in self.targets},
                "retained_upper_bound": str(upper), "query_lower_bound": lower}

    def verify_lower_bound(self, cert):
        """Recompute the rational dual inequality without pricing or search."""
        try:
            return cert == self.lower_bound_certificate(cert["epsilon"], cert["target_prices"], cert["reviewed"])
        except (KeyError, ValueError, TypeError):
            return False

    def plan_refined(self, epsilon, reviewed=None, node_budget=5000,
                     exchange_budget=20000, pricing_rounds=8):
        """Shared-price planning with an independently checkable root bound.

        Float coordinate descent suggests nonnegative integer price directions;
        unchanged rational constraints validate every set and lower bound.
        Pricing is extra preprocessing charged to elapsed time. It can fail to
        find useful directions. The certificate proves only its stated bound;
        additional search may prove a stronger one.
        """
        epsilon = _f(epsilon)
        if epsilon < 0 or any(isinstance(b, bool) or not isinstance(b, int) or b < 0
                              for b in (node_budget, exchange_budget, pricing_rounds)):
            raise ValueError("epsilon and integer budgets must be nonnegative")
        values = self._reviews(reviewed)
        rows = [tuple(F(0) if i in values else w * (hi - lo)
                      for i, (lo, hi), w in zip(self.item_ids, self.intervals, t.weights))
                for t in self.targets]
        if self.status(values) == "TARGET_CONFLICT":
            return self._plan_result((), [sum(row) for row in rows], epsilon, 0,
                                     "NOT_APPLICABLE", "choose_target", values)
        chosen, lower, search = optimize_widths(rows, epsilon, node_budget, exchange_budget, pricing_rounds)
        residual = [sum(row) - sum(row[i] for i in chosen) for row in rows]
        result = self._plan_result(tuple(self.item_ids[i] for i in chosen), residual, epsilon, lower,
                                   "MINIMUM_CARDINALITY" if len(chosen) == lower else "FEASIBLE_WITH_LOWER_BOUND",
                                   "shared_price_group_search", values)
        result.update(search=search, optimality_gap=len(chosen) - lower)
        prices = search.get("dual", {}).get("target_prices", ["0"] * len(self.targets))
        result["lower_bound_certificate"] = self.lower_bound_certificate(
            epsilon, {t.name: p for t, p in zip(self.targets, prices)}, values)
        return result


def from_predictions(preds, better, worse, measurements, aggs=("micro",),
                     domain="unrestricted", item_ids=None, threshold=0):
    """Build a paired review problem; input order must already match by ID.

    Default domains allow any binary-score difference. Opt-in candidate
    domains assume trusted differences stay inside observed per-item scorer
    extrema, including on items where all candidate scorers agree.
    """
    a, b = list(preds[better]["items"]), list(preds[worse]["items"])
    if not a or len(a) != len(b) or any(x[1:] != y[1:] for x, y in zip(a, b)):
        raise ValueError("nonempty paired items with equal gold and metadata are required; no truncation")
    if domain not in ("unrestricted", "candidate") or not measurements:
        raise ValueError("declare measurements and use domain='unrestricted' or 'candidate'")
    pairs = tuple(dict.fromkeys(tuple(p) for p in measurements))
    if any(p not in PARSE or m not in METRIC for p, m in pairs):
        raise ValueError("unknown parser or metric")
    intervals = []
    for x, y in zip(a, b):
        differences = [METRIC[m](PARSE[p](x[0]), x[1], x[2]) -
                       METRIC[m](PARSE[p](y[0]), y[1], y[2]) for p, m in pairs]
        intervals.append((min(differences), max(differences)) if domain == "candidate" else (-1, 1))
    assumptions = ("trusted reviews are correct", "input rows represent the same items in both arms")
    if domain == "candidate":
        assumptions += ("trusted differences lie inside candidate scorer extrema; consensus is not validated",)
    payload = {"better": better, "worse": worse, "a": a, "b": b, "measurements": pairs, "domain": domain}
    digest = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    ids = tuple(item_ids) if item_ids is not None else tuple("item-%04d" % i for i in range(len(a)))
    return ReviewProblem(ids, tuple(intervals), tuple(linear_target([x[2] for x in a], agg) for agg in aggs),
                         assumptions, digest, threshold)
