# SPDX-License-Identifier: MIT
"""Matched-objective comparison; external MILP is optional experiment tooling."""
import argparse
from fractions import Fraction as F
from hashlib import sha256
import json
from math import lcm
from pathlib import Path
import platform
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples"))
from robustband.review import ReviewProblem, Target, linear_target
from review_budget import load_problem


def encode(problem):
    return {"item_ids": problem.item_ids,
            "intervals": [[str(a), str(b)] for a, b in problem.intervals],
            "targets": {t.name: [str(w) for w in t.weights] for t in problem.targets},
            "assumptions": problem.assumptions, "input_digest": problem.input_digest,
            "threshold": str(problem.threshold)}


def decode(raw):
    return ReviewProblem(tuple(raw["item_ids"]), tuple(tuple(d) for d in raw["intervals"]),
                         tuple(Target(k, tuple(v)) for k, v in raw["targets"].items()),
                         assumptions=tuple(raw.get("assumptions", (
                             "trusted reviews lie inside the declared intervals",))),
                         input_digest=raw.get("input_digest", ""), threshold=raw.get("threshold", "0"))


def check_plan(problem, epsilon, plan):
    chosen = set(plan["selected_ids"])
    assert len(chosen) == plan["n_reviews"] and chosen <= set(problem.item_ids)
    widths = {t.name: sum(w * (hi - lo) for name, w, (lo, hi) in zip(
        problem.item_ids, t.weights, problem.intervals) if name not in chosen) for t in problem.targets}
    assert max(widths.values()) <= epsilon
    assert widths == {k: F(v) for k, v in plan["residual_widths"].items()}
    assert plan["width_guaranteed"]


def external_oracle(problem, epsilon):
    """HiGHS numerical optimum; independently recheck its set in rational arithmetic.

    Row-specific integer scaling avoids near-zero constraint coefficients.
    Solver success is an external numerical cross-check, not a formal proof.
    """
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    rows, required = [], []
    for target in problem.targets:
        values = [w * (hi - lo) for w, (lo, hi) in zip(target.weights, problem.intervals)]
        scale = lcm(epsilon.denominator, *(v.denominator for v in values))
        row = [int(v * scale) for v in values]
        rhs = sum(row) - int(epsilon * scale)
        assert max(row + [abs(rhs)]) <= 2 ** 53
        rows.append(row)
        required.append(rhs)
    start = time.perf_counter()
    result = milp(np.ones(len(problem.item_ids)), integrality=np.ones(len(problem.item_ids)),
                  bounds=Bounds(0, 1), constraints=LinearConstraint(rows, required, np.inf),
                  options={"mip_rel_gap": 0.0, "time_limit": 30.0})
    seconds = time.perf_counter() - start
    if not result.success:
        return {"status": int(result.status), "message": result.message, "seconds": seconds}
    assert all(abs(float(x) - round(float(x))) < 1e-6 for x in result.x)
    ids = [name for name, x in zip(problem.item_ids, result.x) if x > 0.5]
    assert all(sum(w * (hi - lo) for name, w, (lo, hi) in zip(
        problem.item_ids, t.weights, problem.intervals) if name not in ids) <= epsilon
               for t in problem.targets)
    return {"status": 0, "n_reviews": len(ids), "selected_ids": ids,
            "seconds": seconds, "exact_feasibility_rechecked": True}


def generated_cases(protocol, seed):
    rng = random.Random(seed)
    for suite in ("dense", "grouped"):
        cfg = protocol["suites"][suite]
        for n in cfg["sizes"]:
            for case in range(cfg["cases_per_size"]):
                intervals = tuple(rng.choice(((-1, 1), (-1, 0), (0, 1))) for _ in range(n))
                if suite == "dense":
                    m = cfg["targets"][case % len(cfg["targets"])]
                    raw = [[rng.randrange(1, 13) for _ in range(n)] for _ in range(m)]
                    targets = tuple(Target(str(j), tuple(F(v, sum(row)) for v in row))
                                    for j, row in enumerate(raw))
                else:
                    metas = [{"class": rng.randrange(cfg["classes"]),
                              "len_bucket": rng.randrange(cfg["length_buckets"])} for _ in range(n)]
                    targets = tuple(linear_target(metas, name) for name in cfg["targets"])
                p = ReviewProblem(tuple("%s-%d-%d-%d" % (suite, n, case, i) for i in range(n)),
                                  intervals, targets)
                yield suite, p, F(cfg["epsilon"][case % len(cfg["epsilon"])])


def compare(suite, problem, epsilon, budget, exchange_budget, oracle, number):
    plans, timings = {}, {}
    order = ("legacy", "optimized") if number % 2 == 0 else ("optimized", "legacy")
    for method in order:
        start = time.perf_counter()
        plan = (problem.plan(epsilon) if method == "legacy"
                else problem.plan_optimized(epsilon, node_budget=budget, exchange_budget=exchange_budget))
        timings[method] = time.perf_counter() - start
        check_plan(problem, epsilon, plan)
        plans[method] = plan
    legacy, optimized = plans["legacy"], plans["optimized"]
    assert optimized["n_reviews"] <= legacy["n_reviews"]
    if legacy["optimality"] == "MINIMUM_CARDINALITY":
        assert optimized["n_reviews"] == legacy["n_reviews"]
    record = {"suite": suite, "epsilon": str(epsilon), "problem": encode(problem),
              "plans": plans, "seconds": timings}
    if oracle:
        external = external_oracle(problem, epsilon)
        record["external_oracle"] = external
        if external["status"] == 0:
            assert optimized["query_lower_bound"] <= external["n_reviews"] <= optimized["n_reviews"]
            if optimized["optimality"] == "MINIMUM_CARDINALITY":
                assert optimized["n_reviews"] == external["n_reviews"]
    return record


def summarize(records):
    def mean(key, method):
        return statistics.mean(r["plans"][method][key] for r in records)
    out = {"n_cases": len(records), "legacy_reviews": mean("n_reviews", "legacy"),
           "optimized_reviews": mean("n_reviews", "optimized"),
           "improved_cases": sum(r["plans"]["optimized"]["n_reviews"] <
                                 r["plans"]["legacy"]["n_reviews"] for r in records)}
    for method in ("legacy", "optimized"):
        out[method + "_certified_cases"] = sum(
            r["plans"][method]["optimality"] == "MINIMUM_CARDINALITY" for r in records)
        out[method + "_mean_gap"] = statistics.mean(
            r["plans"][method]["n_reviews"] - r["plans"][method]["query_lower_bound"] for r in records)
        out[method + "_seconds"] = sum(r["seconds"][method] for r in records)
    out["observed_speed_ratio"] = out["legacy_seconds"] / out["optimized_seconds"]
    out["portfolio_reviews"] = statistics.mean(r["plans"]["optimized"]["search"]["portfolio_reviews"]
                                               for r in records)
    out["exchange_reviews"] = statistics.mean(r["plans"]["optimized"]["search"]["heuristic_reviews"]
                                              for r in records)
    out["search_cutoff_cases"] = sum(r["plans"]["optimized"]["search"]["budget_exhausted"] for r in records)
    checked = [r for r in records if r.get("external_oracle", {}).get("status") == 0]
    if checked:
        out["external_checked_cases"] = len(checked)
        out["optimized_matches_external_cases"] = sum(
            r["plans"]["optimized"]["n_reviews"] == r["external_oracle"]["n_reviews"] for r in checked)
        out["external_seconds"] = sum(r["external_oracle"]["seconds"] for r in checked)
    return out


def verify_artifact(path):
    """Offline source-hash, rational feasibility and deterministic plan replay."""
    data = json.loads(path.read_text(encoding="utf-8"))
    for name, digest in data["input_hashes"].items():
        assert sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest, name
    for case in data["cases"]:
        problem, epsilon = decode(case["problem"]), F(case["epsilon"])
        for method in ("legacy", "optimized"):
            plan = case["plans"][method]
            check_plan(problem, epsilon, plan)
            assert plan["problem_digest"] == problem.fingerprint()
            replay = (problem.plan(epsilon) if method == "legacy" else problem.plan_optimized(
                epsilon, node_budget=plan["search"]["node_budget"],
                exchange_budget=plan["search"]["exchange_budget"]))
            assert replay == plan
    assert data["summary"] == {suite: summarize([r for r in data["cases"] if r["suite"] == suite])
                              for suite in dict.fromkeys(r["suite"] for r in data["cases"])}
    print("[VERIFY PASS] %s: %d cases; source hashes, rational widths and both plans replayed" %
          (data["split"], len(data["cases"])))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "held_out"), default="development")
    parser.add_argument("--external-oracle", action="store_true")
    parser.add_argument("--verify", type=Path, help="Replay an existing artifact offline without SciPy")
    args = parser.parse_args()
    if args.verify:
        return verify_artifact(args.verify)
    protocol_path = ROOT / "experiments/review_optimization_protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    seed = protocol[args.split + "_seed"]
    cases = []
    if args.split == "held_out":
        original = json.loads((ROOT / protocol["suites"]["original"]["source"]).read_text(encoding="utf-8"))
        cases += [("original", decode(r["problem"]), F("1/10")) for r in original["synthetic_cases"]]
    cases += list(generated_cases(protocol, seed))
    if args.split == "held_out":
        for domain in protocol["suites"]["real"]["domains"]:
            p, _ = load_problem(domain)
            cases.append(("real_" + domain, p, F(protocol["suites"]["real"]["epsilon"])))
    records = []
    for number, (suite, problem, epsilon) in enumerate(cases):
        records.append(compare(suite, problem, epsilon, protocol["budget"]["search_nodes"],
                               protocol["budget"]["exchange_checks"], args.external_oracle, number))
        if (number + 1) % 12 == 0:
            print("Completed %d/%d" % (number + 1, len(cases)), flush=True)
    summary = {suite: summarize([r for r in records if r["suite"] == suite])
               for suite in dict.fromkeys(r["suite"] for r in records)}
    paths = ["experiments/review_optimization_protocol.json", "robustband/review_search.py",
             "robustband/review.py", "experiments/review_optimization.py", "tests/test_review_search.py",
             "examples/review_budget.py", "results/review_mechanism_2026-10-12.json",
             "demo/data_real/cot.jsonl", "demo/data_real/plain.jsonl"]
    hashes = {name: sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for name in paths}
    env = {"python": sys.version, "platform": platform.platform()}
    if args.external_oracle:
        import scipy
        env["scipy"] = scipy.__version__
    result = {"schema": protocol["schema"], "split": args.split, "seed": seed,
              "input_hashes": hashes, "environment": env, "summary": summary,
              "human_labels": "NONE", "timing": "One alternating-order local measurement per planner per case",
              "cases": records}
    path = ROOT / ("results/review_optimization_%s_2026-10-12.json" % args.split)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
