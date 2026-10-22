# SPDX-License-Identifier: MIT
"""Offline integration audit of two pinned EvalScope visualization samples.

No generation, no human labels, no population inference, no rerun IFEval grader.
Use --verify to reproduce the entire report, including source/code identities.
"""
import argparse
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import robustband as rb
from robustband.storage import write_json_atomic
from robustband.compiled import CompiledScores
from robustband.review import ReviewProblem, from_predictions, linear_target
from demo.ref_impl import ref_parse, ref_metric


def digest(path):
    return sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def band(tables, better, worse):
    margins = {name: table[better] - table[worse] for name, table in tables.items()}
    lo, hi = min(margins.values()), max(margins.values())
    return {"claim": better + " > " + worse, "n_protocols": len(margins),
            "exact_tables": {k: {m: str(s) for m, s in t.items()} for k, t in tables.items()},
            "exact_margins": {k: str(v) for k, v in margins.items()},
            "exact_band": [str(lo), str(hi)],
            "stability_fraction": str(F(sum(v > 0 for v in margins.values()), len(margins))),
            "break_set": [k for k, v in margins.items() if v <= 0],
            "verdict": "ROBUST" if lo > 0 else "REFUTED" if hi <= 0 else "UNIDENTIFIABLE"}


def review(problem, epsilon):
    plan = problem.plan_refined(epsilon)
    assert problem.verify_certificate(problem.certificate())
    assert problem.verify_lower_bound(plan["lower_bound_certificate"])
    assert max(problem.bounds()[t][1] - problem.bounds()[t][0] -
               sum(problem.targets[j].weights[i] * (hi - lo)
                   for i, (lo, hi) in enumerate(problem.intervals)
                   if problem.item_ids[i] in plan["selected_ids"])
               for j, t in enumerate(problem.bounds())) <= epsilon
    return {"trusted_human_labels": 0, "completion_certificate": problem.certificate(),
            "review_plan": plan}


def run():
    protocol_path = ROOT / "experiments/external_cases_protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    manifest_path = ROOT / "examples/data/evalscope/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for source in manifest["files"]:
        assert digest(ROOT / source["local_path"]) == source["sha256_lf"], source["local_path"]
    assert manifest["revision"] == protocol["source_revision"]
    models = protocol["models"]
    better, worse = "qwen3-max", "qwen-plus"
    epsilon = F(protocol["review"]["epsilon"])
    cases = {}
    for dataset, config in protocol["cases"].items():
        adapter = rb.EvalScopeAdapter({m: ROOT / "examples/data/evalscope" / m /
                                      config["source_file"] for m in models})
        records, preds = adapter.records(), adapter.load()
        n = config["expected_rows_per_model"]
        assert all(len(rows) == n for rows in records.values())
        ids = [dataset + "-" + str(r["sample_id"]) for r in records[better]]
        tables, vectors = {}, {}
        if dataset == "gsm8k":
            family = rb.build_family(parses=config["parses"], metrics=config["metrics"],
                                     aggs=config["aggs"])
            claim = rb.RankClaim(better, worse)
            raw = rb.evaluate(preds, family, claim)
            cached = CompiledScores(preds, family).evaluate(claim)
            assert raw.to_dict() == cached.to_dict()
            for h in family:
                vectors[str(h)] = {}
                tables[str(h)] = {}
                for model, blob in preds.items():
                    reference = [ref_metric(h.metric, ref_parse(h.parse, r), g)
                                 for r, g, meta in blob["items"]]
                    actual = [rb.METRIC[h.metric](rb.PARSE[h.parse](r), g, meta)
                              for r, g, meta in blob["items"]]
                    assert reference == actual
                    vectors[str(h)][model] = reference
                    tables[str(h)][model] = F(sum(reference), n)
            exact = rb.rational.rational_band(preds[better]["items"], preds[worse]["items"], family)
            margins = {key: tables[key][better] - tables[key][worse] for key in tables}
            assert {key: val for key, val, certain in exact["rows"]} == margins
            assert all(abs(raw.margins[k] - float(v)) <= 1e-12 for k, v in margins.items())
            candidate = from_predictions(preds, better, worse,
                [(p, m) for p in config["parses"] for m in config["metrics"]],
                aggs=("micro",), domain="candidate", item_ids=ids)
            checks = {"raw_equals_cached": True, "independent_item_scorer": True,
                      "exact_rational_band": True}
        else:
            for column in config["score_columns"]:
                vectors[column] = {m: [r["scores"][column] for r in rows]
                                   for m, rows in records.items()}
                assert all(s in (0, 1) for vals in vectors[column].values() for s in vals)
                tables[column] = {m: sum(vals, F(0)) / n for m, vals in vectors[column].items()}
            intervals = [(min(v[better][i] - v[worse][i] for v in vectors.values()),
                          max(v[better][i] - v[worse][i] for v in vectors.values())) for i in range(n)]
            candidate = ReviewProblem(tuple(ids), tuple(intervals), (linear_target([{}] * n, "micro"),),
                assumptions=("trusted differences lie in the range of imported strict/loose scores; UNVALIDATED",),
                input_digest=sha256(json.dumps({k: [str(a), str(b)] for k, (a, b) in
                                     zip(ids, intervals)}, sort_keys=True).encode()).hexdigest())
            checks = {"imported_binary_scores": True, "independently_rerun_instruction_grader": False,
                      "exact_rational_aggregation": True}
        unrestricted = ReviewProblem(tuple(ids), ((-1, 1),) * n, candidate.targets,
            assumptions=("trusted differences lie in [-1,1]; no other coverage restriction",),
            input_digest=candidate.input_digest)
        cases[dataset] = {"n_pairs": n, "sample_ids": [r["sample_id"] for r in records[better]],
            "pairing": "equal IDs, input messages (excluding verified final completion), target and metadata",
            "checks": checks, "band": band(tables, better, worse),
            "item_scores": {k: {m: [str(v) for v in vals] for m, vals in t.items()}
                            for k, t in vectors.items()},
            "review": {"epsilon": str(epsilon), "unrestricted": review(unrestricted, epsilon),
                       "candidate_UNVALIDATED": review(candidate, epsilon)}}
    code_paths = [Path(__file__).relative_to(ROOT), Path("demo/ref_impl.py")]
    code_paths += sorted(p.relative_to(ROOT) for p in (ROOT / "robustband").glob("*.py"))
    return {"schema": "robustband.external_cases/v1", "robustband_version": rb.__version__,
            "protocol_sha256_lf": digest(protocol_path), "manifest_sha256_lf": digest(manifest_path),
            "source_revision": manifest["revision"], "code_sha256_lf": {str(p).replace("\\", "/"):
                digest(ROOT / p) for p in code_paths}, "new_model_inference": False,
            "external_adoption_evidence": False, "limits": protocol["limits"], "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / ("results/external_cases_%s.json" % rb.__version__))
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    result = run()
    if args.verify:
        assert result == json.loads(args.verify.read_text(encoding="utf-8")), "report mismatch"
        print("VERIFY PASS: source identity, alignment, exact margins and review certificates")
    else:
        write_json_atomic(args.output, result)
        for name, case in result["cases"].items():
            print(name, case["band"]["exact_band"], case["band"]["verdict"],
                  {k: v["review_plan"]["n_reviews"] for k, v in case["review"].items() if k != "epsilon"})


if __name__ == "__main__":
    main()
