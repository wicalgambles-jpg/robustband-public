# SPDX-License-Identifier: MIT
"""Shared-price review experiment; optional external MILP oracle."""
import argparse
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import platform
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.review_optimization import encode, decode, check_plan, external_oracle
from examples.review_budget import load_problem
from robustband.review import ReviewProblem, Target, linear_target

def digest(path):
    return sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def generated(protocol, seed):
    rng = random.Random(seed)
    for suite in ("dense", "grouped"):
        cfg = protocol["suites"][suite]
        for n in cfg["sizes"]:
            for case in range(cfg["cases_per_size"]):
                intervals = tuple(rng.choice(((-1, 1), (-1, 0), (0, 1))) for _ in range(n))
                if suite == "dense":
                    m = cfg["targets"][case % 2]
                    epsilon = F(cfg["epsilon"][(case // 2) % 2])
                    raw = [[rng.randrange(1, 13) for _ in range(n)] for _ in range(m)]
                    targets = tuple(Target(str(j), tuple(F(v, sum(row)) for v in row))
                                    for j, row in enumerate(raw))
                else:
                    epsilon = F(cfg["epsilon"][case % 2])
                    metas = [{"class": rng.randrange(cfg["classes"]),
                              "len_bucket": rng.randrange(cfg["length_buckets"])} for _ in range(n)]
                    targets = tuple(linear_target(metas, t) for t in cfg["targets"])
                yield suite, ReviewProblem(tuple("%s-%d-%d-%d" % (suite, n, case, i) for i in range(n)),
                                           intervals, targets), epsilon


def run_case(suite, problem, epsilon, config, number, external):
    plans, seconds = {}, {"v1": [], "refined": []}
    for repetition in range(3):
        order = ("v1", "refined") if (number + repetition) % 2 else ("refined", "v1")
        for method in order:
            start = time.perf_counter()
            kwargs = {"node_budget": config["search_nodes"], "exchange_budget": config["exchange_checks"]}
            plan = (problem.plan_optimized(epsilon, **kwargs) if method == "v1" else
                    problem.plan_refined(epsilon, pricing_rounds=config["pricing_rounds"], **kwargs))
            seconds[method].append(time.perf_counter() - start)
            if method in plans:
                assert plans[method] == plan
            plans[method] = plan
    for plan in plans.values():
        check_plan(problem, epsilon, plan)
    cert = plans["refined"]["lower_bound_certificate"]
    start = time.perf_counter()
    assert problem.verify_lower_bound(cert)
    audit_seconds = time.perf_counter() - start
    assert cert["query_lower_bound"] <= plans["refined"]["query_lower_bound"]
    out = {"suite": suite, "epsilon": str(epsilon), "problem": encode(problem), "plans": plans,
           "seconds": {k: statistics.median(v) for k, v in seconds.items()},
           "timing_samples": seconds, "standalone_verify_seconds": audit_seconds}
    if external:
        oracle = external_oracle(problem, epsilon)
        out["external_oracle"] = oracle
        if oracle["status"] == 0:
            for plan in plans.values():
                assert plan["query_lower_bound"] <= oracle["n_reviews"] <= plan["n_reviews"]
                if plan["optimality"] == "MINIMUM_CARDINALITY":
                    assert plan["n_reviews"] == oracle["n_reviews"]
    return out


def summary(cases):
    out = {"n_cases": len(cases), "fewer_reviews": sum(c["plans"]["refined"]["n_reviews"] <
           c["plans"]["v1"]["n_reviews"] for c in cases), "more_reviews": sum(
           c["plans"]["refined"]["n_reviews"] > c["plans"]["v1"]["n_reviews"] for c in cases)}
    for method in ("v1", "refined"):
        out[method + "_reviews"] = statistics.mean(c["plans"][method]["n_reviews"] for c in cases)
        out[method + "_certified"] = sum(c["plans"][method]["optimality"] == "MINIMUM_CARDINALITY" for c in cases)
        out[method + "_gap"] = statistics.mean(c["plans"][method]["n_reviews"] -
                                               c["plans"][method]["query_lower_bound"] for c in cases)
        out[method + "_seconds"] = sum(c["seconds"][method] for c in cases)
        out[method + "_nodes"] = sum(c["plans"][method]["search"]["nodes_visited"] for c in cases)
    standalone = [c for c in cases if c["plans"]["refined"]["lower_bound_certificate"]["query_lower_bound"] ==
                  c["plans"]["refined"]["n_reviews"]]
    out["standalone_minimum_proofs"] = len(standalone)
    out["standalone_verify_seconds"] = sum(c["standalone_verify_seconds"] for c in cases)
    if standalone:
        out["proof_only_vs_replanning_ratio"] = sum(c["seconds"]["refined"] for c in standalone) / sum(
            c["standalone_verify_seconds"] for c in standalone)
    checked = [c for c in cases if c.get("external_oracle", {}).get("status") == 0]
    out["external_checked"] = len(checked)
    if checked:
        out["refined_matches_external"] = sum(c["plans"]["refined"]["n_reviews"] ==
                                               c["external_oracle"]["n_reviews"] for c in checked)
    return out


def verify(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    for name, expected in data["input_hashes"].items():
        assert digest(ROOT / name) == expected, name
    for case in data["cases"]:
        p, epsilon = decode(case["problem"]), F(case["epsilon"])
        for plan in case["plans"].values():
            assert plan["problem_digest"] == p.fingerprint()
            check_plan(p, epsilon, plan)
        refined = case["plans"]["refined"]
        assert p.verify_lower_bound(refined["lower_bound_certificate"])
        assert refined["lower_bound_certificate"]["query_lower_bound"] <= refined["n_reviews"]
    expected = {suite: summary([c for c in data["cases"] if c["suite"] == suite])
                for suite in dict.fromkeys(c["suite"] for c in data["cases"])}
    assert data["summary"] == expected
    count = sum(c["plans"]["refined"]["n_reviews"] == c["plans"]["refined"]["lower_bound_certificate"]
                ["query_lower_bound"] for c in data["cases"])
    print("[VERIFY PASS] %d rational feasible sets and root certificates; %d standalone minima; no optimizer run" %
          (len(data["cases"]), count))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "held_out"), default="development")
    parser.add_argument("--external-oracle", action="store_true")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        return verify(args.verify)
    protocol = json.loads((ROOT / "experiments/review_dual_protocol.json").read_text(encoding="utf-8"))
    cases = list(generated(protocol, protocol[args.split + "_seed"]))
    if args.split == "held_out":
        original = json.loads((ROOT / protocol["suites"]["regression"]["original"]).read_text(encoding="utf-8"))
        cases += [("original", decode(c["problem"]), F("1/10")) for c in original["synthetic_cases"]]
        previous = json.loads((ROOT / protocol["suites"]["regression"]["previous_held_out"]).read_text(encoding="utf-8"))
        cases += [("previous_" + c["suite"], decode(c["problem"]), F(c["epsilon"])) for c in previous["cases"]
                  if c["suite"] in ("dense", "grouped")]
        for domain in protocol["suites"]["real"]["domains"]:
            p, _ = load_problem(domain)
            cases.append(("real_" + domain, p, F(protocol["suites"]["real"]["epsilon"])))
    records = []
    for number, (suite, problem, epsilon) in enumerate(cases):
        records.append(run_case(suite, problem, epsilon, protocol["budget"], number, args.external_oracle))
        if (number + 1) % 12 == 0:
            print("Completed %d/%d" % (number + 1, len(cases)), flush=True)
    paths = ["robustband/review.py", "robustband/review_search.py", "robustband/review_dual.py",
             "experiments/review_dual_benchmark.py", "experiments/review_dual_protocol.json",
             "experiments/review_optimization.py", "tests/test_review_dual.py", "examples/review_budget.py",
             "results/review_mechanism_2026-10-12.json", "results/review_optimization_held_out_2026-10-12.json",
             "demo/data_real/cot.jsonl", "demo/data_real/plain.jsonl"]
    result = {"schema": protocol["schema"], "split": args.split, "seed": protocol[args.split + "_seed"],
              "environment": {"python": sys.version, "platform": platform.platform()},
              "input_hashes": {name: digest(ROOT / name) for name in paths},
              "timing": "Median of three alternating-order runs per planner per case; pricing and certificate construction included",
              "human_labels": "NONE", "summary": {suite: summary([c for c in records if c["suite"] == suite])
               for suite in dict.fromkeys(c["suite"] for c in records)}}
    # Pretty metadata plus one compact, reconstructable JSON case per line.
    output = json.dumps(result, indent=2, ensure_ascii=False)[:-2] + ',\n  "cases": [\n'
    output += ',\n'.join('    ' + json.dumps(c, ensure_ascii=False, separators=(',', ':')) for c in records)
    output += '\n  ]\n}\n'
    path = ROOT / ("results/review_dual_%s_2026-10-12.json" % args.split)
    path.write_text(output, encoding="utf-8")
    print(json.dumps(result["summary"], indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
