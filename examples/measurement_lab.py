# SPDX-License-Identifier: MIT
"""Editable general-edition adapter: aggregation algorithms and exact parameters.

Run ``python examples/measurement_lab.py ui`` to include this trusted extension.
The professional edition continues to offer the original text evaluator.
"""
from decimal import Decimal, InvalidOperation
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
import re
from statistics import median
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from robustband.audit_engine import assemble, display, exact, validate_names
from robustband.domains import AuditDomain, register_domain
from robustband.scores import load_scores, normalize_scores, preview_scores, DEMO_CSV, REQUIRED

SCHEMA = "robustband.measurement_lab/v1"
DEFAULTS = {"algorithms":["mean", "median", "trimmed_mean"], "trim_each_side":"1", "trim_side":"both", "minimum_advantage":"0", "note":""}


def _parameters(family, n):
    if not isinstance(family, dict) or set(family) != set(DEFAULTS):
        raise ValueError("Declare algorithms, trim_each_side, trim_side, minimum_advantage and note.")
    algorithms = family["algorithms"]
    if (not isinstance(algorithms, list) or not algorithms or
            any(a not in ("mean", "median", "trimmed_mean") for a in algorithms) or len(set(algorithms)) != len(algorithms)):
        raise ValueError("Choose distinct supported algorithms.")
    count = family["trim_each_side"]
    if not isinstance(count, str) or not re.fullmatch(r"\d{1,4}", count):
        raise ValueError("trim_each_side must be an integer decimal string.")
    count = int(count)
    side = family["trim_side"]
    if side not in ("both", "upper", "lower"):
        raise ValueError("Choose trim_side both, upper or lower.")
    if "trimmed_mean" in algorithms and (2*count if side == "both" else count) >= n:
        raise ValueError("Trimming must leave at least one observation per model.")
    threshold = family["minimum_advantage"]
    if not isinstance(threshold, str) or len(threshold) > 256:
        raise ValueError("minimum_advantage must be a finite nonnegative decimal string.")
    try:
        number = Decimal(threshold)
    except InvalidOperation as exc:
        raise ValueError("Invalid minimum_advantage.") from exc
    if not number.is_finite() or number < 0 or abs(number.as_tuple().exponent) > 128 or abs(number.adjusted()) > 128:
        raise ValueError("minimum_advantage must be finite and nonnegative, with a bounded exponent.")
    if not isinstance(family["note"], str):
        raise ValueError("note must be a string.")
    return count, F(number)


def analyze(rows, family=None, model_a="A", model_b="B"):
    rows = normalize_scores(rows)
    validate_names(model_a, model_b)
    settings = DEFAULTS if family is None else family
    if isinstance(settings, dict):
        settings = {k:list(v) if isinstance(v,list) else v for k,v in settings.items()}
    count, threshold = _parameters(settings, len(rows))
    sign = 1 if rows[0]["direction"] == "higher" else -1
    unit = rows[0]["unit"]
    margin_unit = "pp" if unit == "percent" else unit
    vectors = [[F(Decimal(r[side])) for r in rows] for side in ("score_a", "score_b")]
    configurations = []
    for algorithm in settings["algorithms"]:
        scores = []
        for vector in vectors:
            selected = vector
            if algorithm == "trimmed_mean" and count:
                selected = sorted(vector)
                start = count if settings["trim_side"] in ("both", "lower") else 0
                end = len(selected)-count if settings["trim_side"] in ("both", "upper") else len(selected)
                selected = selected[start:end]
            scores.append(median(selected) if algorithm == "median" else sum(selected,F(0))/len(selected))
        a, b = scores
        margin = sign*(a-b)-threshold
        configurations.append({"protocol":algorithm, "score_a":exact(a), "score_b":exact(b), "margin":exact(margin),
            "supports":margin>0, "all_zero":a==b==0, "display_score_a":display(a)+" "+unit,
            "display_score_b":display(b)+" "+unit, "display_margin":display(margin)+" "+margin_unit})
    report = assemble(SCHEMA, rows, settings, model_a, model_b, configurations, ("scores.py", "input_utils.py"), [], [
        "This is an editable example extension, not a validated improvement to the professional evaluator.",
        "Positive margin means A's oriented advantage strictly exceeds minimum_advantage, in the supplied score units.",
        "Trimming sorts and removes values within each model separately. The selected observations can differ; choose policies before inspecting outcomes.",
        "Recorded measurements and upstream rounding are not independently validated. No population inference is performed."])
    report["extension_source_sha256_lf"] = {"examples/measurement_lab.py":sha256(Path(__file__).read_bytes().replace(b"\r\n",b"\n")).hexdigest()}
    report["claim"].update(kind="minimum_advantage", direction=rows[0]["direction"], minimum_advantage=exact(threshold))
    report["claim"]["description"] = model_a+"'s oriented advantage over "+model_b+" strictly exceeds "+exact(threshold)+" "+margin_unit
    bounds = [F(v) for v in report["result"]["exact_band"]]
    report["result"].update(display_band=[display(v)+" "+margin_unit for v in bounds], plot_band=[float(v) for v in bounds],
        plot_extent=float(max(F(1),*(abs(v) for v in bounds))), plot_unit=margin_unit, plot_scale=1,
        target_description=rows[0]["metric"]+" / "+unit+" / "+rows[0]["direction"]+". Required advantage: "+exact(threshold)+" "+margin_unit)
    report["sections"] = [{"title":"Declared extension parameters", "columns":["Parameter", "Value"],
                           "rows":[[k,v] for k,v in settings.items() if k!="algorithms"]}]
    return report


def verify(report):
    if not isinstance(report,dict) or report.get("schema") != SCHEMA:
        raise ValueError("Unsupported measurement-lab schema.")
    try:
        actual = analyze(report["inputs"],report["family"],report["claim"]["model_a"],report["claim"]["model_b"])
    except (KeyError,TypeError) as exc:
        raise ValueError("Incomplete measurement-lab report.") from exc
    if actual != report:
        raise ValueError("Report mismatch: use the recorded core and unchanged extension, data, algorithms and parameters.")
    return True


def register():
    title = lambda en,zh:{"en":en,"zh":zh}
    metadata = {"title":title("Measurement lab (editable extension)","指标实验室（可修改扩展）"), "fields":list(REQUIRED),
        "defaults":DEFAULTS, "example":DEMO_CSV, "example_format":"csv", "preview_fields":["sample_id","score_a","score_b","group"],
        "note":title("Choose algorithms and exact parameters. This extension illustrates adaptation; justify your policies independently.",
                     "可选择算法并配置精确参数。本扩展示范领域改造，参数与协议的合理性需要独立判断。"),
        "controls":[{"key":"algorithms","kind":"checks","title":title("Aggregation algorithms","汇总算法"),
            "options":[{"value":a,"title":title(a,a)} for a in ("mean","median","trimmed_mean")]},
            {"key":"trim_each_side","kind":"number","title":title("Trim count (integer)","移除数量（整数）")},
            {"key":"trim_side","kind":"select","title":title("Trimming side","移除哪一端"),
             "options":[{"value":a,"title":title(a,a)} for a in ("both","upper","lower")]},
            {"key":"minimum_advantage","kind":"number","title":title("Required strict advantage (score units)","严格优势阈值（原分数单位）")},
            {"key":"note","kind":"text","title":title("Policy note","协议说明")}]}
    register_domain(AuditDomain("measurement_lab",SCHEMA,("csv","jsonl"),load_scores,preview_scores,analyze,verify,metadata))


if __name__ == "__main__":
    register()
    from robustband.cli import main
    raise SystemExit(main())
