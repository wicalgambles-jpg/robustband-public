# SPDX-License-Identifier: MIT
"""Audits of recorded paired scalar measurements, with exact decimal input.

One metric, unit and optimization direction per audit. Raw predictions need a
domain adapter to calculate scores; this module never infers their meaning.
"""
from decimal import Decimal, InvalidOperation
from fractions import Fraction as F
import re
from statistics import median

from .audit_engine import assemble, display, exact, validate_names
from .audit_engine import LIMITS
from .input_utils import MAX_BYTES, MAX_ROWS, read_table

REQUIRED = ("sample_id", "score_a", "score_b", "metric", "unit", "direction")
AGGREGATIONS = ("mean", "median", "group_mean")
DEFAULT_FAMILY = {"aggregations": ["mean", "median"]}
DEMO_CSV = ("sample_id,score_a,score_b,metric,unit,direction,group\n"
            "small-1,9,10,latency,ms,lower,small\n"
            "small-2,9,10,latency,ms,lower,small\n"
            "large-1,110,100,latency,ms,lower,large\n")


def _number(value):
    if type(value) not in (str, int, Decimal):
        raise ValueError("Scores must be decimal strings or integers; avoid binary floats in the Python API.")
    text = str(value).strip()
    if len(text) > 512 or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
        raise ValueError("Use a finite decimal score, without NaN, infinity or missing values.")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal score.") from exc
    if len(number.as_tuple().digits) > 256 or abs(number.as_tuple().exponent) > 128 or abs(number.adjusted()) > 128:
        raise ValueError("Score precision or magnitude exceeds the supported decimal limits.")
    return text


def normalize_scores(rows):
    normalized, seen, target = [], set(), None
    for number, row in enumerate(rows, 1):
        if number > MAX_ROWS:
            raise ValueError("Use at most %d paired score records." % MAX_ROWS)
        if not isinstance(row, dict) or not set(REQUIRED) <= row.keys():
            raise ValueError("Record %d needs fields: %s." % (number, ", ".join(REQUIRED)))
        identity = row["sample_id"]
        if type(identity) not in (str, int) or not str(identity).strip() or str(identity) in seen:
            raise ValueError("Record %d has an invalid or duplicate sample_id." % number)
        seen.add(str(identity))
        if any(not isinstance(row[k], str) or not row[k].strip() for k in ("metric", "unit", "direction")):
            raise ValueError("Declare a nonempty metric, unit and direction on every record.")
        current = tuple(row[k].strip() for k in ("metric", "unit", "direction"))
        if current[2] not in ("higher", "lower"):
            raise ValueError("direction must be higher or lower.")
        if target is not None and current != target:
            raise ValueError("Do not mix metrics, units or directions in one audit.")
        target = current
        group = row.get("group", "")
        if not isinstance(group, str):
            raise ValueError("group must be an explicit string label.")
        normalized.append(dict(sample_id=str(identity), score_a=_number(row["score_a"]), score_b=_number(row["score_b"]),
                               metric=current[0], unit=current[1], direction=current[2], group=group))
    if not normalized:
        raise ValueError("Input has no paired score records.")
    return normalized


def load_scores(text, format="csv"):
    """JSON numbers are read as decimal strings before any float conversion."""
    return normalize_scores(read_table(text, format, REQUIRED, MAX_BYTES, MAX_ROWS, exact_decimals=True))


def preview_scores(rows):
    rows = normalize_scores(rows)
    return {"n_items": len(rows), "records": rows[:5], "group_available": all(r["group"].strip() for r in rows),
            "measurement": {k: rows[0][k] for k in ("metric", "unit", "direction")}}


def analyze_scores(rows, family=None, model_a="A", model_b="B"):
    rows = normalize_scores(rows)
    validate_names(model_a, model_b)
    settings = DEFAULT_FAMILY if family is None else family
    if not isinstance(settings, dict) or set(settings) != {"aggregations"}:
        raise ValueError("Declare aggregations for the score protocol family.")
    aggs = settings["aggregations"]
    if (not isinstance(aggs, list) or not aggs or any(not isinstance(a, str) or a not in AGGREGATIONS for a in aggs)
            or len(set(aggs)) != len(aggs)):
        raise ValueError("Choose distinct supported aggregations: mean, median, group_mean.")
    if "group_mean" in aggs and any(not r["group"].strip() for r in rows):
        raise ValueError("group_mean requires an explicit nonempty group on every record.")
    values = {side: [F(Decimal(r[side])) for r in rows] for side in ("score_a", "score_b")}
    sign = 1 if rows[0]["direction"] == "higher" else -1
    groups = sorted({r["group"] for r in rows})
    configurations = []
    unit = " " + rows[0]["unit"]
    margin_unit = "pp" if rows[0]["unit"] == "percent" else rows[0]["unit"]
    for aggregation in aggs:
        scores = []
        for side, vector in values.items():
            units = vector
            if aggregation == "group_mean":
                units = [[v for r, v in zip(rows, vector) if r["group"] == group] for group in groups]
                units = [sum(group, F(0))/len(group) for group in units]
            scores.append(median(vector) if aggregation == "median" else sum(units, F(0))/len(units))
        a, b = scores
        margin = sign * (a - b)
        configurations.append({"protocol": aggregation, "score_a": exact(a), "score_b": exact(b),
                               "margin": exact(margin), "supports": margin > 0, "all_zero": a == b == 0,
                               "display_score_a": display(a) + unit, "display_score_b": display(b) + unit,
                               "display_margin": display(margin) + " " + margin_unit})
    distinct = len({(c["score_a"], c["score_b"]) for c in configurations})
    warnings = [] if distinct == len(configurations) else ["Some policies produce identical scores; protocol counts are not independent votes."]
    report = assemble("robustband.scores_audit/v1", rows, {"aggregations": list(aggs)}, model_a, model_b,
                      configurations, ("scores.py", "input_utils.py"), warnings, list(LIMITS) + [
                          "Recorded scores are audited without recalculating the original metric or validating its measurement process.",
                          "One metric, unit and direction per audit. Positive oriented margins favor A: A-B for higher, B-A for lower.",
                          "group_mean averages within each group, then gives every group equal weight. Median compares model medians; it is not the median paired difference."])
    measurement = {k: rows[0][k] for k in ("metric", "unit", "direction")}
    measurement["margin_unit"] = margin_unit
    report["measurement"] = measurement
    report["claim"]["kind"] = "strict_preference"
    report["claim"]["direction"] = rows[0]["direction"]
    bounds = [F(v) for v in report["result"]["exact_band"]]
    report["result"].update(display_band=[display(v) + " " + margin_unit for v in bounds], plot_band=[float(v) for v in bounds],
                            plot_extent=float(max(F(1), *(abs(v) for v in bounds))), plot_unit=margin_unit, plot_scale=1,
                            distinct_score_pairs=distinct)
    report["result"]["target_description"] = " / ".join(measurement.values()) + ". Positive oriented margins favor A; display is rounded."
    report["sections"] = [{"title": "Measurement target", "columns": ["Metric", "Unit", "Preferred direction", "Positive margin"],
                           "rows": [[measurement["metric"], measurement["unit"], measurement["direction"], "A-B" if sign == 1 else "B-A"]]}]
    return report


def verify_scores_report(report):
    if not isinstance(report, dict) or report.get("schema") != "robustband.scores_audit/v1":
        raise ValueError("Unsupported recorded-score audit schema.")
    try:
        actual = analyze_scores(report["inputs"], report["family"], report["claim"]["model_a"], report["claim"]["model_b"])
    except (KeyError, TypeError) as exc:
        raise ValueError("Incomplete recorded-score audit report.") from exc
    if actual != report:
        raise ValueError("Report mismatch: use the recorded version and unchanged scores, units, direction and policies.")
    return True
