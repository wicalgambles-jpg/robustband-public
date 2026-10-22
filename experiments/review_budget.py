# SPDX-License-Identifier: MIT
"""Frozen exploratory benchmark of identical worst-case width objectives."""
from fractions import Fraction as F
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples"))
from robustband.review import ReviewProblem, Target
from review_budget import load_problem


def widths(problem, selected):
    """Independent full-record weighted-width calculation for baselines."""
    return [sum(w * (hi - lo) for i, (w, (lo, hi)) in enumerate(zip(t.weights, problem.intervals))
                if i not in selected) for t in problem.targets]


def active_items(problem):
    return [i for i, (lo, hi) in enumerate(problem.intervals)
            if lo < hi and any(t.weights[i] for t in problem.targets)]


def until_precision(problem, order, epsilon):
    chosen = set()
    for i in order:
        if max(widths(problem, chosen)) <= epsilon:
            break
        chosen.add(i)
    if max(widths(problem, chosen)) > epsilon:
        raise AssertionError("baseline did not attain the declared precision")
    return len(chosen)


def compare(problem, epsilon, random_orders, rng):
    active = active_items(problem)
    plan = problem.plan(epsilon)
    selected = {problem.item_ids.index(i) for i in plan["selected_ids"]}
    assert max(widths(problem, selected)) <= epsilon
    assert plan["width_guaranteed"]
    if len(active) <= 10:
        optimum = next(k for k in range(len(active) + 1) if any(
            max(widths(problem, set(q))) <= epsilon for q in combinations(active, k)))
        assert plan["optimality"] == "MINIMUM_CARDINALITY" and plan["n_reviews"] == optimum
    orders = []
    for _ in range(random_orders):
        order = active[:]
        rng.shuffle(order)
        orders.append(until_precision(problem, order, epsilon))
    unweighted = sorted(active, key=lambda i: (-(problem.intervals[i][1] - problem.intervals[i][0]), i))
    greedy = problem.plan(epsilon, exact_limit=0)
    return {"plan": plan, "all_ambiguous": len(active), "random_mean": statistics.mean(orders) if orders else 0,
            "random_min": min(orders, default=0), "random_max": max(orders, default=0),
            "unweighted_width": until_precision(problem, unweighted, epsilon),
            "minimax_greedy": greedy["n_reviews"], "greedy_optimality": greedy["optimality"]}


def main():
    protocol_path = ROOT / "experiments/review_protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    cfg = protocol["synthetic"]
    rng = random.Random(cfg["seed"])
    synthetic = []
    for number in range(cfg["n_problems"]):
        n = cfg["n_items"]
        intervals = tuple(rng.choice(((-1, 1), (-1, 0), (0, 1), (0, 0))) for _ in range(n))
        targets = []
        for j in range(3):
            raw = [rng.randrange(1, 13) for _ in range(n)]
            targets.append(Target("target-%d" % j, tuple(F(v, sum(raw)) for v in raw)))
        p = ReviewProblem(tuple("s%d-%d" % (number, i) for i in range(n)), intervals, tuple(targets))
        result = compare(p, F(cfg["epsilon"]), cfg["random_orders_per_problem"], rng)
        result["problem"] = {"item_ids": p.item_ids, "intervals": [[str(x) for x in d] for d in p.intervals],
                             "targets": {t.name: [str(x) for x in t.weights] for t in p.targets}}
        synthetic.append(result)
    summary = {key: statistics.mean(r[key] if key != "exact_plan" else r["plan"]["n_reviews"] for r in synthetic)
               for key in ("exact_plan", "all_ambiguous", "random_mean", "unweighted_width", "minimax_greedy")}
    summary["exact_beats_greedy_cases"] = sum(r["plan"]["n_reviews"] < r["minimax_greedy"] for r in synthetic)
    real = {}
    for domain in ("unrestricted", "candidate"):
        p, _ = load_problem(domain)
        cfg_real = protocol["real"]
        real[domain] = compare(p, F(cfg_real["epsilon"]), cfg_real["random_orders"],
                               random.Random(cfg_real["seed"]))
        real[domain]["assumptions"] = p.assumptions
    hashes = {}
    for name in ("demo/data_real/cot.jsonl", "demo/data_real/plain.jsonl", "experiments/review_protocol.json"):
        hashes[name] = sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    out = {"schema": protocol["schema"], "date": protocol["frozen_date"], "input_hashes": hashes,
           "synthetic_summary": summary, "real_planning_only": real, "synthetic_cases": synthetic,
           "human_adjudication": "NONE", "novelty_status": "PRIOR_ALGORITHMS; CANDIDATE_INTEGRATION_ONLY"}
    output = ROOT / "results/review_mechanism_2026-10-12.json"
    output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"synthetic": summary, "real": {k: {name: r[name] for name in (
        "all_ambiguous", "random_mean", "unweighted_width", "minimax_greedy")} |
        {"exact_plan": r["plan"]["n_reviews"]} for k, r in real.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
