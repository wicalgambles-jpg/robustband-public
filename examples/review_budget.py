# SPDX-License-Identifier: MIT
"""Dry-run review planning on the frozen 24-item GSM8K paired prefix.

No new labels are generated. Optional --labels accepts a JSON object mapping
gsm8k-test-NNNN IDs to trusted cot-minus-plain correctness differences.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import robustband as rb
from robustband.review import from_predictions


def load_problem(domain="unrestricted"):
    preds = {}
    for name, expected in (("cot", 30), ("plain", 24)):
        rows = [json.loads(line) for line in (ROOT / "demo/data_real" / (name + ".jsonl"))
                .read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(rows) != expected:
            raise ValueError("frozen paired files changed")
        # This explicitly declared prefix is the existing experiment's 24 pairs.
        preds[name] = {"items": [(r["raw"], r["gold"], r["meta"]) for r in rows[:24]]}
    pairs = [(p, m) for p in rb.PARSE for m in rb.METRIC]
    ids = ["gsm8k-test-%04d" % i for i in range(24)]
    problem = from_predictions(preds, "cot", "plain", pairs,
                               aggs=("micro", "macro_class", "macro_len"),
                               domain=domain, item_ids=ids)
    return problem, preds


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--domain", choices=("unrestricted", "candidate"), default="unrestricted")
    ap.add_argument("--epsilon", default="1/20")
    ap.add_argument("--planner", choices=("refined", "optimized", "legacy"), default="refined")
    ap.add_argument("--node-budget", type=int, default=5000)
    ap.add_argument("--exchange-budget", type=int, default=20000)
    ap.add_argument("--pricing-rounds", type=int, default=8)
    ap.add_argument("--labels", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--template", type=Path)
    args = ap.parse_args()
    p, preds = load_problem(args.domain)
    labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else {}
    cert = p.certificate(labels)
    if args.planner == "refined":
        plan = p.plan_refined(args.epsilon, labels, args.node_budget, args.exchange_budget, args.pricing_rounds)
    else:
        plan = (p.plan_optimized(args.epsilon, labels, args.node_budget, args.exchange_budget)
                if args.planner == "optimized" else p.plan(args.epsilon, labels))
    reference = {}
    for i, (a, b) in enumerate(zip(preds["cot"]["items"], preds["plain"]["items"])):
        reference[p.item_ids[i]] = (rb.METRIC["exact_match"](rb.PARSE["last_line_num"](a[0]), a[1], a[2])
                                    - rb.METRIC["exact_match"](rb.PARSE["last_line_num"](b[0]), b[1], b[2]))
    result = {"domain": args.domain, "n_items": 24, "human_labels_provided": bool(labels),
              "planner": args.planner,
              "completion_certificate": cert, "review_plan": plan,
              "fixed_scorer_diagnostic": {"measurement": "last_line_num|exact_match",
                  "independent_human_adjudication": False,
                  "target_margins": {k: str(lo) for k, (lo, _) in p.bounds(reference).items()},
                  "status": p.status(reference)}}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.template:
        questions = json.loads((ROOT / "demo/data/items.json").read_text(encoding="utf-8"))
        rows = []
        for item_id in plan["selected_ids"]:
            i = p.item_ids.index(item_id)
            rows.append({"item_id": item_id, "question": questions[i]["q"], "gold": questions[i]["gold"],
                         "cot_output": preds["cot"]["items"][i][0], "plain_output": preds["plain"]["items"][i][0],
                         "declared_difference_domain": [str(x) for x in p.intervals[i]],
                         "trusted_difference": None, "reviewer": None, "evidence": None})
        args.template.parent.mkdir(parents=True, exist_ok=True)
        args.template.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("mode=%s status=%s planned_reviews=%d optimality=%s" %
          (args.domain, cert["status"], plan["n_reviews"], plan["optimality"]))
    if "optimality_gap" in plan:
        print("certified_lower_bound=%d gap=%d search_nodes=%d" %
              (plan["query_lower_bound"], plan["optimality_gap"], plan["search"]["nodes_visited"]))
    if "lower_bound_certificate" in plan:
        proof = plan["lower_bound_certificate"]
        print("standalone_root_lower_bound=%d verified=%s" %
              (proof["query_lower_bound"], p.verify_lower_bound(proof)))
    print("reference scorer only: %s %s" %
          (result["fixed_scorer_diagnostic"]["target_margins"], result["fixed_scorer_diagnostic"]["status"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
