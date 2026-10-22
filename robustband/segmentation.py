# SPDX-License-Identifier: MIT
"""Exact IoU audits from paired confusion counts, with explicit class targets."""
from fractions import Fraction as F
import json

from .audit_engine import assemble, validate_names, exact as _exact, display as _display
from .audit_engine import STRICT_RANK_EXPLANATIONS as EXPLANATIONS
from .input_utils import MAX_BYTES, MAX_ROWS, read_table

AGGREGATIONS = ("pooled", "image_mean", "group_mean")
EMPTY_CLASSES = ("zero", "omit")
DEMO_ROWS = [
    {"sample_id": "small-1", "group": "small", "confusion_a": [[9, 0], [0, 1]], "confusion_b": [[9, 0], [1, 0]]},
    {"sample_id": "small-2", "group": "small", "confusion_a": [[9, 0], [0, 1]], "confusion_b": [[9, 0], [1, 0]]},
    {"sample_id": "large-1", "group": "large", "confusion_a": [[900, 0], [100, 0]], "confusion_b": [[900, 0], [0, 100]]},
]
DEMO_JSONL = "".join(json.dumps(row) + "\n" for row in DEMO_ROWS)


def normalize_confusions(rows):
    """Rows are true labels, columns predicted labels; class totals must match."""
    normalized, seen, dimension = [], set(), None
    for number, row in enumerate(rows, 1):
        if number > MAX_ROWS:
            raise ValueError("Use at most %d paired confusion records." % MAX_ROWS)
        if not isinstance(row, dict) or not {"sample_id", "confusion_a", "confusion_b"} <= row.keys():
            raise ValueError("Record %d needs sample_id, confusion_a and confusion_b." % number)
        identity = row["sample_id"]
        if type(identity) not in (str, int) or not str(identity).strip() or str(identity) in seen:
            raise ValueError("Record %d has an invalid or duplicate sample_id." % number)
        identity = str(identity)
        seen.add(identity)
        matrices = []
        for key in ("confusion_a", "confusion_b"):
            matrix = row[key]
            if (not isinstance(matrix, list) or not 2 <= len(matrix) <= 64 or
                    any(not isinstance(r, list) or len(r) != len(matrix) for r in matrix)):
                raise ValueError("%s must be a square matrix with 2 to 64 classes." % key)
            if any(type(n) is not int or not 0 <= n <= 2**63-1 for r in matrix for n in r):
                raise ValueError("Confusion entries must be nonnegative 64-bit integer counts.")
            matrices.append([list(r) for r in matrix])
        a, b = matrices
        if len(a) != len(b) or (dimension is not None and len(a) != dimension):
            raise ValueError("Every matrix must use the same class dimension.")
        dimension = len(a)
        if [sum(r) for r in a] != [sum(r) for r in b] or sum(map(sum, a)) == 0:
            raise ValueError("Paired matrices need identical nonempty ground-truth class totals.")
        group = row.get("group", "")
        if not isinstance(group, str):
            raise ValueError("group must be an explicit string label.")
        names = row.get("class_names", [str(k) for k in range(dimension)])
        if (not isinstance(names, list) or len(names) != dimension or
                any(not isinstance(n, str) or not n.strip() for n in names) or len(set(names)) != dimension):
            raise ValueError("class_names must contain one distinct nonempty name per class.")
        if normalized and names != normalized[0]["class_names"]:
            raise ValueError("Class names and order must match across records.")
        normalized.append({"sample_id": identity, "group": group, "class_names": list(names),
                           "confusion_a": a, "confusion_b": b})
    if not normalized:
        raise ValueError("Input has no paired confusion records.")
    return normalized


def load_confusions(text):
    return normalize_confusions(read_table(text, "jsonl", (), MAX_BYTES, MAX_ROWS))


def preview_confusions(rows):
    rows = normalize_confusions(rows)
    return {"n_items": len(rows), "n_classes": len(rows[0]["class_names"]),
            "class_names": rows[0]["class_names"], "group_available": all(r["group"].strip() for r in rows),
            "records": [{"sample_id": r["sample_id"], "group": r["group"], "pixels": sum(map(sum, r["confusion_a"]))}
                        for r in rows[:5]]}


def _pool(matrices):
    n = len(matrices[0])
    return [[sum(m[i][j] for m in matrices) for j in range(n)] for i in range(n)]


def _iou(matrix, classes, empty):
    values = []
    undefined = 0
    for k in classes:
        tp = matrix[k][k]
        union = sum(matrix[k]) + sum(r[k] for r in matrix) - tp
        if union:
            values.append(F(tp, union))
        else:
            undefined += 1
            if empty == "zero":
                values.append(F(0))
    return (sum(values, F(0))/len(values) if values else None), undefined


def analyze_confusions(rows, family=None, model_a="A", model_b="B"):
    rows = normalize_confusions(rows)
    validate_names(model_a, model_b)
    n = len(rows[0]["class_names"])
    settings = {"classes": None, "aggregations": ["pooled", "image_mean"], "empty_classes": ["zero"]} if family is None else family
    if not isinstance(settings, dict) or set(settings) != {"classes", "aggregations", "empty_classes"}:
        raise ValueError("Declare classes, aggregations and empty_classes.")
    classes = list(range(n)) if settings["classes"] is None else settings["classes"]
    if (not isinstance(classes, list) or not classes or any(type(k) is not int or not 0 <= k < n for k in classes)
            or len(set(classes)) != len(classes)):
        raise ValueError("Select distinct valid class indices; use null for all classes.")
    for key, allowed in (("aggregations", AGGREGATIONS), ("empty_classes", EMPTY_CLASSES)):
        values = settings[key]
        if (not isinstance(values, list) or not values or any(not isinstance(v, str) or v not in allowed for v in values)
                or len(set(values)) != len(values)):
            raise ValueError("Choose distinct supported options for " + key + ".")
    settings = {"classes": list(classes), "aggregations": list(settings["aggregations"]),
                "empty_classes": list(settings["empty_classes"])}
    if "group_mean" in settings["aggregations"] and any(not r["group"].strip() for r in rows):
        raise ValueError("group_mean requires an explicit nonempty group on every record.")
    # Build counts once; policy evaluation only changes averaging and empty-class rules.
    pooled = {side: _pool([r[side] for r in rows]) for side in ("confusion_a", "confusion_b")}
    groups = sorted({r["group"] for r in rows})
    units = {"pooled": {side: [m] for side, m in pooled.items()},
             "image_mean": {side: [r[side] for r in rows] for side in pooled}}
    if "group_mean" in settings["aggregations"]:
        units["group_mean"] = {side: [_pool([r[side] for r in rows if r["group"] == group]) for group in groups]
                               for side in pooled}
    configurations, margins, warnings = [], [], []
    for aggregation in settings["aggregations"]:
        for empty in settings["empty_classes"]:
            scores, defined, undefined = [], [], []
            for side in pooled:
                values = [_iou(matrix, classes, empty) for matrix in units[aggregation][side]]
                valid = [score for score, count in values if score is not None]
                if not valid:
                    raise ValueError("Selected classes are undefined in every unit under omit; choose a present target or an explicit zero convention.")
                scores.append(sum(valid, F(0))/len(valid))
                defined.append(len(valid))
                undefined.append(sum(count for score, count in values))
            a, b = scores
            margin = a-b
            margins.append(margin)
            if undefined != [0, 0]:
                warnings.append("%s/%s: undefined class-units A=%d, B=%d; defined averaging units A=%d, B=%d. Omission can change model-specific denominators." %
                                (aggregation, empty, *undefined, *defined))
            configurations.append({"protocol": aggregation + "|empty=" + empty, "score_a": _exact(a),
                                   "score_b": _exact(b), "margin": _exact(margin), "supports": margin > 0,
                                   "all_zero": a == b == 0, "defined_units": defined, "undefined_class_units": undefined,
                                   "display_score_a": _display(a, True) + "%", "display_score_b": _display(b, True) + "%",
                                   "display_margin": _display(margin, True) + " pp"})
    lo, hi = min(margins), max(margins)
    diagnostics = []
    for k in classes:
        truth = sum(pooled["confusion_a"][k])
        a, b = (m[k][k] for m in pooled.values())
        diagnostics.append({"class_index": k, "class_name": rows[0]["class_names"][k],
                            "ground_truth_pixels": truth, "true_positive_a": a, "true_positive_b": b})
        if truth and (a == 0 or b == 0):
            warnings.append("Class %s has ground-truth pixels but zero true positives on %s." %
                            (rows[0]["class_names"][k], "both sides" if a == b == 0 else "A" if a == 0 else "B"))
    distinct = len({(r["score_a"], r["score_b"]) for r in configurations})
    if distinct < len(configurations):
        warnings.append("Some policies produce identical scores on this data; protocol counts are not independent votes.")
    sources = ("segmentation.py", "input_utils.py")
    report = assemble("robustband.segmentation_audit/v1", rows, settings, model_a, model_b,
            configurations, sources, warnings,
            ["IoU uses rows=true and columns=predicted. Classes and aggregation targets are explicitly declared.",
                       "Exact decisions use rational counts; displayed percentages/plots are rounded, and margins use percentage points (pp).",
                       "Confusion counts do not verify spatial pairing or annotation quality; the matrix producer must check matching inputs and ground truth.",
                       "This is an audit of supplied records, not model inference, human adjudication or a population confidence interval."], EXPLANATIONS)
    report["result"].update(display_band=[_display(lo, True) + " pp", _display(hi, True) + " pp"],
                            plot_band=[float(lo), float(hi)], plot_extent=1, plot_unit="pp", plot_scale=100,
                            selected_class_names=[rows[0]["class_names"][k] for k in classes], distinct_score_pairs=distinct)
    report["result"]["target_description"] = "Selected classes: " + ", ".join(report["result"]["selected_class_names"]) + ". Rounded display in pp; exact fractions in JSON."
    report["class_diagnostics"] = diagnostics
    report["sections"] = [{"title": "Selected class diagnostics", "columns": ["Class", "Ground-truth pixels", "True positive A", "True positive B"],
                           "rows": [[d[k] for k in ("class_name", "ground_truth_pixels", "true_positive_a", "true_positive_b")] for d in diagnostics]}]
    return report


def verify_segmentation_report(report):
    if not isinstance(report, dict) or report.get("schema") != "robustband.segmentation_audit/v1":
        raise ValueError("Unsupported segmentation audit schema.")
    try:
        actual = analyze_confusions(report["inputs"], report["family"], report["claim"]["model_a"], report["claim"]["model_b"])
    except (KeyError, TypeError) as exc:
        raise ValueError("Incomplete segmentation audit report.") from exc
    if actual != report:
        raise ValueError("Report mismatch: use the recorded version and unchanged confusion counts/policies.")
    return True
