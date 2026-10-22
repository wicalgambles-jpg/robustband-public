# SPDX-License-Identifier: MIT
"""Explicit adoption criteria over separate, exactly evaluated domain targets.

Each target owns its protocol family and oriented threshold. No cross-metric
average, population interval or automatic policy selection is introduced.
"""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path

from . import __version__
from .audit_engine import display, exact, validate_names
from .domains import get_domain
from .input_utils import MAX_BYTES, MAX_ROWS, read_table
from .scores import _number, normalize_scores

SCHEMA = "robustband.decision/v1"
PLAN_SCHEMA = "robustband.decision_plan/v1"
MAX_TARGETS = 16
EXAMPLE = ("seed,overall_a,overall_b,human_a,human_b\n"
           "s1,52,50,7,8\ns2,53,50,8,9\ns3,54,50,8,10\n")
EXAMPLE_MAPPING = {"sample_id": "seed", "group": None, "metrics": [
    {"metric": "mIoU", "score_a": "overall_a", "score_b": "overall_b", "unit": "percent", "direction": "higher"},
    {"metric": "Human_IoU", "score_a": "human_a", "score_b": "human_b", "unit": "percent", "direction": "higher"}]}
EXAMPLE_PLAN = {"schema": PLAN_SCHEMA, "domain": "scores", "name": "Candidate adoption",
    "rationale": "Require an overall gain while bounding the Human-class regression. Synthetic example.",
    "targets": [
        {"id": "overall", "label": "Overall quality", "role": "primary", "metric": "mIoU",
         "unit": "percent", "direction": "higher",
         "family": {"aggregations": ["mean", "median"]}, "threshold": "1", "operator": "gt",
         "reason": "Inspect both mean and median across the same paired seeds."},
        {"id": "human", "label": "Human-class protection", "role": "guardrail", "metric": "Human_IoU",
         "unit": "percent", "direction": "higher",
         "family": {"aggregations": ["mean", "median"]}, "threshold": "-0.5", "operator": "ge",
         "reason": "Use the same seed cohort; allow at most 0.5 percentage points of regression."}]}


def _digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError(name + " must be a nonempty string of at most 2000 characters.")
    return value


def validate_plan(plan, edition="generalized"):
    """Require explicit criteria and reasons; adapters validate their own policies."""
    if not isinstance(plan, dict) or set(plan) != {"schema", "domain", "name", "rationale", "targets"} or plan["schema"] != PLAN_SCHEMA:
        raise ValueError("Use a complete robustband.decision_plan/v1 plan with domain, name, rationale and targets.")
    if plan["domain"] not in ("text", "segmentation", "scores"):
        raise ValueError("Decision plans support text, segmentation or scores.")
    get_domain(plan["domain"], edition)
    _text(plan["name"], "Plan name")
    _text(plan["rationale"], "Plan rationale")
    targets = plan["targets"]
    if not isinstance(targets, list) or not 1 <= len(targets) <= MAX_TARGETS:
        raise ValueError("Declare between 1 and 16 decision targets.")
    seen = set()
    for target in targets:
        keys = {"id", "label", "role", "family", "threshold", "operator", "reason"}
        if plan["domain"] == "scores":
            keys.update(("metric", "unit", "direction"))
        if not isinstance(target, dict) or set(target) != keys:
            raise ValueError("Each target needs id, label, role, family, threshold, operator, reason and (for scores) metric, unit, direction.")
        for key in ("id", "label", "reason"):
            _text(target[key], "Target " + key)
        if target["id"] in seen:
            raise ValueError("Decision target IDs must be unique.")
        seen.add(target["id"])
        if target["role"] not in ("primary", "guardrail") or target["operator"] not in ("gt", "ge"):
            raise ValueError("Use role primary/guardrail and operator gt/ge.")
        if not isinstance(target["threshold"], str):
            raise ValueError("Target threshold must be an exact decimal string in the oriented margin unit.")
        _number(target["threshold"])
        if not isinstance(target["family"], dict):
            raise ValueError("Declare a protocol family object for each target.")
        if "metric" in keys:
            for key in ("metric", "unit", "direction"):
                _text(target[key], "Target " + key)
            if target["direction"] not in ("higher", "lower"):
                raise ValueError("Target direction must be higher or lower.")
    if sum(t["role"] == "primary" for t in targets) != 1:
        raise ValueError("Declare exactly one primary target; additional targets are guardrails.")
    return deepcopy(plan)


def inspect_columns(text, format="csv"):
    """Read header names without guessing measurement or pairing semantics."""
    rows = read_table(text, format, max_bytes=MAX_BYTES, max_rows=MAX_ROWS, exact_decimals=True)
    if not rows or any(not isinstance(r, dict) for r in rows):
        raise ValueError("Input must contain table records with named columns.")
    columns = list(rows[0])
    if any(set(r) != set(columns) for r in rows):
        raise ValueError("All imported records must have the same column names.")
    return {"columns": columns, "n_records": len(rows)}


def _score_groups(text, format, mapping):
    rows = read_table(text, format, max_bytes=MAX_BYTES, max_rows=MAX_ROWS, exact_decimals=True)
    if mapping is not None:
        if not isinstance(mapping, dict) or set(mapping) != {"sample_id", "group", "metrics"}:
            raise ValueError("Mapping needs sample_id, group (column or null), and metrics.")
        _text(mapping["sample_id"], "Sample ID column")
        if mapping["group"] is not None:
            _text(mapping["group"], "Group column")
        metrics = mapping["metrics"]
        if not isinstance(metrics, list) or not 1 <= len(metrics) <= MAX_TARGETS:
            raise ValueError("Map between 1 and 16 metrics.")
        expanded, names = [], set()
        for metric in metrics:
            if not isinstance(metric, dict) or set(metric) != {"metric", "score_a", "score_b", "unit", "direction"}:
                raise ValueError("Each mapped metric needs metric, score_a, score_b, unit and direction.")
            for key in metric:
                _text(metric[key], "Mapped " + key)
            if metric["metric"].strip() in names or metric["score_a"] == metric["score_b"]:
                raise ValueError("Map distinct metric names and distinct A/B score columns.")
            names.add(metric["metric"].strip())
            required = [mapping["sample_id"], metric["score_a"], metric["score_b"]] + ([mapping["group"]] if mapping["group"] else [])
            for row in rows:
                if not isinstance(row, dict) or not set(required) <= row.keys():
                    raise ValueError("Mapped columns are missing from a source record.")
                expanded.append(dict(sample_id=row[mapping["sample_id"]], score_a=row[metric["score_a"]],
                    score_b=row[metric["score_b"]], metric=metric["metric"], unit=metric["unit"],
                    direction=metric["direction"], group=row[mapping["group"]] if mapping["group"] else ""))
        if len(expanded) > MAX_ROWS:
            raise ValueError("Mapped input exceeds the 5000 measurement-record limit.")
        rows = expanded
    groups = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("metric"), str) or not row["metric"].strip():
            raise ValueError("Each numeric record needs a metric; use the paired template or map your columns.")
        groups.setdefault(row["metric"].strip(), []).append(row)
    if not groups:
        raise ValueError("Input has no paired measurement records.")
    return {name: normalize_scores(values) for name, values in groups.items()}


def preview_decision(text, domain="scores", format="csv", mapping=None, edition="generalized"):
    """Describe available targets before evaluating any adoption criterion."""
    adapter = get_domain(domain, edition)
    if format not in adapter.formats:
        raise ValueError("Choose a supported input format for this domain.")
    if domain == "scores":
        groups = _score_groups(text, format, mapping)
        return {"metrics": [dict(metric=name, unit=rows[0]["unit"], direction=rows[0]["direction"],
                    n_items=len(rows), group_available=all(r["group"].strip() for r in rows)) for name, rows in groups.items()]}
    if mapping is not None:
        raise ValueError("Column mapping applies to numeric scores only.")
    return adapter.preview(adapter.load(text, format))


def analyze_decision(text, plan, format="csv", mapping=None, model_a="A", model_b="B", edition="generalized"):
    """Apply every declared condition, preserving separate targets and units."""
    plan = validate_plan(plan, edition)
    validate_names(model_a, model_b)
    domain = plan["domain"]
    adapter = get_domain(domain, edition)
    if format not in adapter.formats:
        raise ValueError("Choose a supported input format for this domain.")
    groups = _score_groups(text, format, mapping) if domain == "scores" else None
    if groups is None:
        if mapping is not None:
            raise ValueError("Column mapping applies to numeric scores only.")
        common = adapter.load(text, format)
    outputs, cohort = [], None
    selected = {t["metric"] for t in plan["targets"]} if groups is not None else set()
    if groups is not None and not selected <= groups.keys():
        raise ValueError("A selected target metric is missing from the input.")
    for target in plan["targets"]:
        rows = groups[target["metric"]] if groups is not None else common
        if groups is not None and any(target[k] != rows[0][k] for k in ("unit", "direction")):
            raise ValueError("Target unit or direction differs from the frozen plan; update the data or explicitly revise the criteria.")
        identities = {r["sample_id"]: r.get("group", "") for r in rows}
        if cohort is not None and identities != cohort:
            raise ValueError("All selected targets must use the same sample IDs and group labels; no implicit inner join is performed.")
        cohort = identities
        audit = adapter.analyze(rows, target["family"], model_a, model_b)
        threshold = F(Decimal(target["threshold"]))
        margins = [F(c["margin"]) for c in audit["configurations"]]
        unit = audit.get("measurement", {}).get("margin_unit", audit["result"].get("plot_unit", "score"))
        scale = F(100) if domain == "segmentation" else F(1)
        # Segmentation margins are fractions; thresholds use the displayed pp unit.
        threshold /= scale
        meets = [m > threshold if target["operator"] == "gt" else m >= threshold for m in margins]
        status = "PASS" if all(meets) else "FAIL" if not any(meets) else "REVIEW"
        lo, hi = min(margins), max(margins)
        outputs.append({"id": target["id"], "status": status, "unit": unit,
            "exact_threshold": exact(threshold), "exact_slack_band": [exact(lo-threshold), exact(hi-threshold)],
            "display_margin_band": [display(lo*scale), display(hi*scale)],
            "display_threshold": display(threshold*scale),
            "meets_count": sum(meets), "n_protocols": len(meets),
            "failing_protocols": [c["protocol"] for c, ok in zip(audit["configurations"], meets) if not ok],
            "audit": audit})
    status = "FAIL" if any(o["status"] == "FAIL" for o in outputs) else "PASS" if all(o["status"] == "PASS" for o in outputs) else "REVIEW"
    primary_ok = any(t["role"] == "primary" and o["status"] == "PASS" for t, o in zip(plan["targets"], outputs))
    tradeoff = primary_ok and any(t["role"] == "guardrail" and o["status"] == "FAIL" for t, o in zip(plan["targets"], outputs))
    root = Path(__file__).parent
    return {"schema": SCHEMA, "software_version": __version__, "model_a": model_a, "model_b": model_b,
        "input": {"text": text, "format": format, "mapping": deepcopy(mapping)},
        "input_sha256": sha256(text.encode("utf-8")).hexdigest(), "plan": plan, "plan_sha256": _digest(plan),
        "source_sha256_lf": {name: sha256((root/name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                              for name in ("decision.py", "domains.py", "input_utils.py", "audit_engine.py")},
        "result": {"status": status, "n_items": len(cohort), "n_targets": len(outputs), "target_tradeoff": tradeoff},
        "unselected_metrics": sorted(set(groups or {}) - selected), "targets": outputs,
        "limits": ["Criteria apply to the supplied paired records and declared per-target protocols.",
                   "PASS: all criteria hold under every selected rule. FAIL: at least one criterion fails under every rule for that target. REVIEW: remaining rule-sensitive cases.",
                   "Different objectives remain separate; an objective tradeoff is not a within-target protocol reversal.",
                   "Protocol ranges are not confidence intervals. Sampling uncertainty and future deployment outcomes require separate evidence.",
                   "Saving a plan records its contents; it does not prove preregistration or scientific appropriateness.",
                   "Replay JSON includes the complete original input file and mapping. Review it before sharing."]}


def verify_decision(report, edition="generalized"):
    """Recompute the entire report, including source mapping and nested audits."""
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise ValueError("Unsupported decision report schema.")
    try:
        source = report["input"]
        rebuilt = analyze_decision(source["text"], report["plan"], source["format"], source["mapping"],
                                   report["model_a"], report["model_b"], edition)
    except (KeyError, TypeError) as exc:
        raise ValueError("Incomplete decision report.") from exc
    except ValueError as exc:
        raise ValueError("Decision replay mismatch: " + str(exc)) from exc
    if rebuilt != report:
        raise ValueError("Decision replay mismatch: input, mapping, criteria, results, version or source hashes changed.")
    return True
