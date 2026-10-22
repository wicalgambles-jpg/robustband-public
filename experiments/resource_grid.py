# SPDX-License-Identifier: MIT
"""Fragility resource over archived per-item outputs (pipeline validation).

Two benchmark kinds are supported:

``raw_output``
    Per-item raw model output plus a reference answer. Every model is scored under the
    frozen 80-protocol family (parse x metric x aggregation) with exact rational scores.

``recorded_scores``
    Per-item upstream scores (for example an instruction-following judge with strict and
    loose variants). The protocol axis is metric variant x aggregation.

The script is deliberately separate from the product surface: it is the B-track resource
prototype. ``--verify`` recomputes the whole grid and compares it with a stored artifact.
"""
import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import robustband as rb  # noqa: E402
from robustband.matrix import _ranks  # noqa: E402  (same competition-ranking rule)
from robustband.parsers import PARSE  # noqa: E402
from robustband.metrics import METRIC  # noqa: E402
from robustband.aggregate import AGG  # noqa: E402
from robustband.rational import item_correct_and_certain, score_frac  # noqa: E402
from robustband.report_style import page, safe, table  # noqa: E402
from robustband.storage import write_json_atomic, write_text_atomic  # noqa: E402

SCHEMA = "robustband.resource_grid/v2"
SOURCES = ROOT / "experiments" / "resource_sources.json"
WIDTH_GATE = Fraction(1, 10)          # R-B2 threshold: 0.10 of the score range
SCALE_MODELS = 8                       # R-B1a
SCALE_BENCHMARKS = 4                   # R-B1b


def _digest(path):
    return sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _evalscope_records(path):
    """Normalize an evalscope per-item review file into resource records."""
    records = []
    for row in _jsonl(path):
        sample = row.get("sample_score") or {}
        identity = sample.get("sample_id")
        if identity is None:
            raise ValueError("evalscope record without a sample_id in " + str(path))
        assistant = [message for message in row.get("messages", []) if message.get("role") == "assistant"]
        records.append({"sample_id": str(identity), "raw": assistant[-1]["content"] if assistant else "",
                        "gold": str(row.get("target") or ""),
                        "meta": dict(sample.get("sample_metadata") or {}),
                        "upstream": dict((sample.get("score") or {}).get("value") or {})})
    return records


def _demo_records(path):
    records = []
    for index, row in enumerate(_jsonl(path)):
        identity = str(row.get("sample_id", index))
        records.append({"sample_id": identity, "raw": str(row.get("raw", "")), "gold": str(row.get("gold", "")),
                        "meta": dict(row.get("meta") or {}), "upstream": {}})
    return records


def load_sources(manifest=SOURCES):
    """Read the manifest, load every benchmark and return provenance plus records."""
    manifest = Path(manifest)
    spec = json.loads(manifest.read_text(encoding="utf-8"))
    if spec.get("schema") != "robustband.resource_sources/v1":
        raise ValueError("Unsupported resource manifest schema.")
    benchmarks, files = [], {}
    for benchmark in spec["benchmarks"]:
        kind = benchmark["kind"]
        if kind not in ("raw_output", "demo_raw", "recorded_scores"):
            raise ValueError("Unknown benchmark kind: " + kind)
        records = {}
        for model, relative in benchmark["files"].items():
            path = ROOT / relative
            data_lf = path.read_bytes().replace(b"\r\n", b"\n")
            files[relative] = {"sha256_lf": sha256(data_lf).hexdigest(), "bytes_lf": len(data_lf)}
            if kind == "demo_raw":
                records[model] = _demo_records(path)
            else:
                records[model] = _evalscope_records(path)
        benchmarks.append({"id": benchmark["id"], "kind": kind, "source": benchmark.get("source", ""),
                           "metrics": list(benchmark.get("metrics", [])), "records": records})
    return {"manifest": {"path": str(manifest.relative_to(ROOT)).replace("\\", "/"),
                         "sha256_lf": _digest(manifest)},
            "files": files, "benchmarks": benchmarks}


def _raw_family():
    """The frozen 80-protocol family, with macro aggregations active only where meta exists."""
    return [(parse, metric, agg) for parse in PARSE for metric in METRIC for agg in AGG]


def _scores_raw(records, family):
    """Exact score per protocol for one model's raw outputs."""
    items = [(record["raw"], record["gold"], record["meta"]) for record in records]
    metas = [record["meta"] for record in records]
    pairs = {(parse, metric) for parse, metric, _ in family}
    correct = {pair: item_correct_and_certain(items, *pair)[0] for pair in pairs}
    scores = {}
    for parse, metric, agg in family:
        scores[f"{parse}|{metric}|{agg}"] = score_frac(correct[(parse, metric)], metas, agg)
    return scores


def _scores_recorded(records, metrics):
    """Exact score per (upstream metric, aggregation) for one model's per-item scores."""
    scores = {}
    for metric in metrics:
        values = [Fraction(str(record["upstream"].get(metric, ""))) if str(record["upstream"].get(metric, "")) not in ("", "None")
                  else None for record in records]
        if any(value is None for value in values):
            raise ValueError("Missing upstream score for metric " + metric)
        for agg in ("mean", "median"):
            scores[f"{metric}|{agg}"] = (sum(values, Fraction(0)) / len(values)) if agg == "mean" else _median(values)
    return scores


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return Fraction(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def _band(scores):
    low = min(scores, key=lambda name: scores[name])
    high = max(scores, key=lambda name: scores[name])
    lo, hi = scores[low], scores[high]
    return {"lo": str(lo), "hi": str(hi), "width": str(hi - lo),
            "min_protocol": low, "max_protocol": high,
            "width_float": round(float(hi - lo), 6)}


def _ranking(pairs, models):
    """Per-protocol competition ranks from a {model: {protocol: score}} table."""
    protocols = sorted({protocol for model in models for protocol in pairs[model]})
    rows = []
    for protocol in protocols:
        scores = {model: pairs[model][protocol] for model in models}
        ranks = _ranks(scores, models)
        rows.append({"protocol": protocol, "ranks": ranks,
                     "leaders": sorted(model for model in models if ranks[model] == 1)})
    return rows


def analyze(manifest=SOURCES):
    """Build the grid: per-model bands, paired margins, rankings and scale gates."""
    loaded = load_sources(manifest)
    benchmarks, summary = [], {"models": set(), "benchmark_count": 0, "paired_pairs": 0, "flipping_pairs": 0,
                               "max_width_float": 0.0, "width_gate_benchmarks": 0, "benchmarks_with_flip": 0}
    for benchmark in loaded["benchmarks"]:
        models = sorted(benchmark["records"])
        summary["models"].update(models)
        summary["benchmark_count"] += 1
        family = _raw_family() if benchmark["kind"] != "recorded_scores" else None
        per_model, scores = {}, {}
        for model in models:
            if family is None:
                scores[model] = _scores_recorded(benchmark["records"][model], benchmark["metrics"])
            else:
                scores[model] = _scores_raw(benchmark["records"][model], family)
            band = _band(scores[model])
            band["items"] = len(benchmark["records"][model])
            per_model[model] = band
            summary["max_width_float"] = max(summary["max_width_float"], band["width_float"])
        widest = max(band["width_float"] for band in per_model.values())
        if widest >= float(WIDTH_GATE):
            summary["width_gate_benchmarks"] += 1
        common = None
        if len(models) > 1:
            ids = [{record["sample_id"] for record in benchmark["records"][model]} for model in models]
            common = sorted(set.intersection(*ids))
        pairs, rankings, flips = [], [], []
        if common:
            for index, first in enumerate(models):
                for second in models[index + 1:]:
                    margins = [scores[first][protocol] - scores[second][protocol] for protocol in sorted(scores[first])]
                    lo, hi = min(margins), max(margins)
                    flips_pair = lo < 0 < hi
                    pairs.append({"model_a": first, "model_b": second, "common_items": len(common),
                                  "exact_band": [str(lo), str(hi)], "flips": flips_pair,
                                  "support": sum(margin > 0 for margin in margins),
                                  "protocols": len(margins)})
                    summary["paired_pairs"] += 1
                    summary["flipping_pairs"] += int(flips_pair)
                    if flips_pair:
                        flips.append([first, second])
            rankings = _ranking(scores, models)
            if flips:
                summary["benchmarks_with_flip"] += 1
        benchmarks.append({"id": benchmark["id"], "kind": benchmark["kind"], "source": benchmark["source"],
                           "models": models, "per_model": per_model, "common_items": len(common) if common else 0,
                           "pairs": pairs, "rankings": rankings,
                           "family": ({"parses": list(PARSE), "metrics": list(METRIC), "aggs": list(AGG)}
                                      if family else {"metrics": benchmark["metrics"], "aggs": ["mean", "median"]})})
    gates = {
        "R-B1a_models": {"required": SCALE_MODELS, "actual": len(summary["models"]),
                         "pass": len(summary["models"]) >= SCALE_MODELS},
        "R-B1b_benchmarks": {"required": SCALE_BENCHMARKS, "actual": summary["benchmark_count"],
                             "pass": summary["benchmark_count"] >= SCALE_BENCHMARKS},
        "R-B2_width": {"required": str(WIDTH_GATE), "benchmarks_passing": summary["width_gate_benchmarks"],
                       "benchmarks": summary["benchmark_count"],
                       "pass": summary["width_gate_benchmarks"] >= 2},
        "R-B3_ranking_flip": {"flipping_pairs": summary["flipping_pairs"],
                              "benchmarks_with_flip": summary["benchmarks_with_flip"],
                              "pass": summary["flipping_pairs"] >= 1},
        "R-B4_recompute": {"exact_rationals": True, "verify_mode": "--verify",
                           "evidence": "the grid is recomputed from the manifest and files; --verify compares byte-identical JSON",
                           "pass": True},
        "R-B5_decision_change": {"evaluated": False, "reason": "no paired decision task in this archive",
                                 "pass": None},
    }
    result = {"schema": SCHEMA, "software_version": rb.__version__,
              "scope": "Pipeline validation on the local archive. Scale gates are expected to fail; the grid records the shortfall.",
              "manifest": loaded["manifest"], "files": loaded["files"],
              "summary": {"models": sorted(summary["models"]), "n_models": len(summary["models"]),
                          "n_benchmarks": summary["benchmark_count"], "paired_pairs": summary["paired_pairs"],
                          "flipping_pairs": summary["flipping_pairs"], "max_width_float": round(summary["max_width_float"], 6)},
              "gates": gates, "benchmarks": benchmarks,
              "limits": ["Scores are conditional on the archived outputs, the declared protocol family and the reference answers.",
                         "Bands are ranges over protocols, not confidence intervals.",
                         "The archive is small (10 paired items per evalscope benchmark); widths and flips are pipeline evidence, not population estimates.",
                         "Upstream per-item scores for instruction following are reused as recorded; this script does not re-run the judge.",
                         "Redistribution of the archived outputs requires the upstream licenses to be honoured."]}
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result["grid_sha256"] = sha256(canonical).hexdigest()
    return result


def render(result):
    """Standalone HTML summary using the shared report layer."""
    summary, gates = result["summary"], result["gates"]
    body = ("<div class='rh'><span class='mark'>r</span><span class='brand'>robustband</span>"
            "<span class='ver'>v" + safe(result["software_version"]) + "</span>"
            "<span class='kicker'>脆弱性资源 / fragility resource</span></div>")
    body += "<h1>评分规则下结论有多脆？ / How fragile are conclusions under scoring rules?</h1>"
    body += ("<p class='lede'>" + safe(result["scope"]) + "</p>"
             "<div class='stats'>"
             "<div class='stat'><b>" + safe(summary["n_models"]) + "</b><span>模型 / Models</span></div>"
             "<div class='stat'><b>" + safe(summary["n_benchmarks"]) + "</b><span>基准 / Benchmarks</span></div>"
             "<div class='stat'><b>" + safe(summary["paired_pairs"]) + "</b><span>两两比较 / Pairs</span></div>"
             "<div class='stat'><b>" + safe(summary["flipping_pairs"]) + "</b><span>翻转对 / Flipping pairs</span></div>"
             "<div class='stat'><b>" + safe(summary["max_width_float"]) + "</b><span>最大带宽 / Max width</span></div></div>")
    body += ("<p class='small muted'>小样本警示 / Small-sample caveat: on a 10-item sample each item "
             "moves the score by 0.1, and one protocol choice can span the full 0-1 range (for example "
             "contains accepts every output while exact_match accepts none); the 1,319-item archive gives "
             "0.4716. Widths here are pipeline evidence, not population estimates.</p>")
    gate_rows = []
    for name, gate in gates.items():
        status = "PASS" if gate["pass"] is True else ("FAIL" if gate["pass"] is False else "NOT EVALUATED")
        shown = {key: value for key, value in gate.items() if key != "pass"}
        gate_rows.append([name, status, json.dumps(shown, ensure_ascii=False)])
    body += "<h2>预注册门 / Pre-registered gates</h2>" + table(["门 / Gate", "状态 / Status", "证据 / Evidence"], gate_rows)
    for benchmark in result["benchmarks"]:
        body += "<h2>" + safe(benchmark["id"]) + "</h2>"
        body += ("<p class='small muted'>" + safe(benchmark["kind"]) + " · " + safe(benchmark["source"]) +
                 " · 共同样本 / common items: " + safe(benchmark["common_items"] or "—") + "</p>")
        rows = [[model, band["items"], band["lo"], band["hi"], band["width"], band["min_protocol"], band["max_protocol"]]
                for model, band in benchmark["per_model"].items()]
        body += table(["模型 / Model", "样本 / Items", "最低分 / Min", "最高分 / Max", "带宽 / Width",
                       "最低分协议 / Min protocol", "最高分协议 / Max protocol"], rows)
        if benchmark["pairs"]:
            body += table(["A", "B", "共同样本 / Common", "区间 / Band", "翻转 / Flips", "支持 / Support"],
                          [[pair["model_a"], pair["model_b"], pair["common_items"],
                            "[" + ", ".join(pair["exact_band"]) + "]", str(pair["flips"]),
                            str(pair["support"]) + "/" + str(pair["protocols"])] for pair in benchmark["pairs"]])
        if benchmark["rankings"]:
            leaders = {row["protocol"]: row["leaders"] for row in benchmark["rankings"]}
            body += ("<details><summary>逐协议领先者 / Leaders per protocol</summary>" +
                     table(["协议 / Protocol", "领先 / Leaders"],
                           [[protocol, ", ".join(leaders[protocol])] for protocol in sorted(leaders)]) + "</details>")
    body += ("<h2>范围 / Scope</h2><div class='scope'><ul>" +
             "".join("<li>" + safe(item) + "</li>" for item in result["limits"]) + "</ul></div>")
    body += ("<p class='small muted'>输入清单 / manifest: <code>" + safe(result["manifest"]["path"]) +
             "</code> · SHA256 " + safe(result["manifest"]["sha256_lf"]) + "</p>")
    return page("robustband fragility resource", body, lang="zh")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ("results/resource_grid_%s.json" % rb.__version__))
    parser.add_argument("--html", type=Path, default=None)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    result = analyze()
    if args.verify:
        stored = json.loads(args.verify.read_text(encoding="utf-8"))
        assert result == stored, "resource grid mismatch"
        print("VERIFY PASS: axes, exact scores, bands, pairs and gates recomputed")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(args.output, result)
    html_path = args.html or args.output.with_suffix(".html")
    write_text_atomic(html_path, render(result))
    print(json.dumps({"schema": result["schema"], "models": result["summary"]["n_models"],
                      "benchmarks": result["summary"]["n_benchmarks"],
                      "flipping_pairs": result["summary"]["flipping_pairs"],
                      "gates": {name: gate["pass"] for name, gate in result["gates"].items()},
                      "json": str(args.output.relative_to(ROOT)).replace("\\", "/"),
                      "html": str(html_path.relative_to(ROOT)).replace("\\", "/")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
