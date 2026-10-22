# SPDX-License-Identifier: MIT
"""Trusted Python adapters share transport, reports and replay dispatch.

Registration is explicit in the Python process. Data files and browser uploads
cannot load code. Each adapter owns its measurement semantics and verifier.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
import json
import re
from typing import Callable

from . import workflow, segmentation, scores
from .parsers import PARSE
from .metrics import METRIC
from .aggregate import AGG


@dataclass(frozen=True)
class AuditDomain:
    id: str
    schema: str
    formats: tuple
    load: Callable
    preview: Callable
    analyze: Callable
    verify: Callable
    metadata: dict


_DOMAINS = {}
EDITIONS = ("professional", "generalized")


def _edition(edition):
    if edition not in EDITIONS:
        raise ValueError("Choose edition professional or generalized.")


def register_domain(domain):
    """Register an adapter once; reject ambiguous IDs or report schemas."""
    if (not isinstance(domain, AuditDomain) or not isinstance(domain.id, str) or
            not re.fullmatch(r"[a-z][a-z0-9_]*", domain.id) or not isinstance(domain.schema, str) or not domain.schema):
        raise ValueError("Use an AuditDomain with a valid ID and nonempty report schema.")
    if (not isinstance(domain.formats, tuple) or not domain.formats or any(f not in ("csv", "jsonl") for f in domain.formats)
            or len(set(domain.formats)) != len(domain.formats)
            or any(not callable(getattr(domain, name)) for name in ("load", "preview", "analyze", "verify"))):
        raise ValueError("Adapters need supported formats and callable load, preview, analyze and verify operations.")
    if domain.id in _DOMAINS or any(d.schema == domain.schema for d in _DOMAINS.values()):
        raise ValueError("Domain ID and report schema must be unique.")
    metadata = domain.metadata
    if (not isinstance(metadata, dict) or not {"title", "fields", "defaults", "controls", "example", "example_format", "preview_fields"} <= metadata.keys()
            or {"id", "schema", "formats"} & metadata.keys() or metadata["example_format"] not in domain.formats):
        raise ValueError("Provide title, fields, defaults, controls, example, example_format and preview_fields metadata.")
    try:
        json.dumps(metadata, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Domain metadata must be JSON serializable.") from exc
    _DOMAINS[domain.id] = AuditDomain(domain.id, domain.schema, domain.formats, domain.load, domain.preview,
                                    domain.analyze, domain.verify, deepcopy(metadata))


def get_domain(domain_id, edition="generalized"):
    _edition(edition)
    if not isinstance(domain_id, str) or domain_id not in _DOMAINS:
        raise ValueError("Unknown audit domain; choose: " + ", ".join(_DOMAINS))
    if edition == "professional" and domain_id != "text":
        raise ValueError("The professional edition uses the original text evaluation domain; use generalized for domain extensions.")
    return replace(_DOMAINS[domain_id], metadata=deepcopy(_DOMAINS[domain_id].metadata))


def domain_options(edition="generalized"):
    """Serializable UI descriptors; callers cannot mutate registered metadata."""
    _edition(edition)
    return [dict(id=d.id, schema=d.schema, formats=list(d.formats), **deepcopy(d.metadata))
            for d in _DOMAINS.values() if edition == "generalized" or d.id == "text"]


def load_domain(domain_id, text, format=None):
    domain = get_domain(domain_id)
    format = domain.formats[0] if format is None else format
    if format not in domain.formats:
        raise ValueError("Domain %s supports input formats: %s." % (domain_id, ", ".join(domain.formats)))
    return domain.load(text, format)


def preview_domain(domain_id, text, format=None):
    domain = get_domain(domain_id)
    return domain.preview(load_domain(domain_id, text, format))


def audit_domain(domain_id, text, format=None, family=None, model_a="A", model_b="B"):
    domain = get_domain(domain_id)
    return domain.analyze(load_domain(domain_id, text, format), family, model_a, model_b)


def verify_audit(report, edition="generalized"):
    """Dispatch by schema; each verifier recomputes its entire bound report."""
    if isinstance(report, dict) and report.get("schema") == "robustband.decision/v1":
        from .decision import verify_decision
        return verify_decision(report, edition)
    if isinstance(report, dict) and report.get("schema") == "robustband.matrix_audit/v1":
        from .matrix import verify_matrix_report
        return verify_matrix_report(report)
    if isinstance(report, dict):
        for domain in _DOMAINS.values():
            if report.get("schema") == domain.schema:
                return get_domain(domain.id, edition).verify(report)
    raise ValueError("Unsupported audit report schema; register its trusted adapter first.")


def _labels(en, zh):
    return {"en": en, "zh": zh}


def _checks(key, title, options, name=None):
    return {"key": key, "kind": "checks", "title": title, "name": name or key,
            "options": [{"value": v, "title": _labels(v, v)} for v in options]}


text_controls = [_checks("parses", _labels("Answer extraction", "答案提取"), PARSE),
                 _checks("metrics", _labels("Item correctness", "单项判定"), METRIC),
                 _checks("aggs", _labels("Aggregation", "分数汇总"), AGG)]
for option in text_controls[2]["options"]:
    if option["value"] in workflow.GROUPS:
        option["requires"] = "group_fields_complete." + workflow.GROUPS[option["value"]]
text_labels = {
    "strict_exact": ("Unmodified output", "原始输出"), "first_num": ("First number", "第一个数字"),
    "last_num": ("Last number", "最后一个数字"), "last_line_num": ("Last-line number", "末行数字"),
    "boxed": ("Boxed answer / fallback", "框内答案 / 回退"), "exact_match": ("Exact match", "精确匹配"),
    "contains": ("Reference substring", "包含参考答案"), "f1_token": ("Token overlap criterion", "词元重合判定"),
    "numeric_tol": ("Exact-decimal tolerance", "精确十进制容差"), "micro": ("Equal item weights", "各题等权"),
    "macro_class": ("Equal class weights", "各类别等权"), "macro_len": ("Equal length-group weights", "各长度组等权"),
    "median": ("Median item correctness", "单项正确性中位数")}
for control in text_controls:
    for option in control["options"]:
        option["title"] = _labels(*text_labels[option["value"]])

register_domain(AuditDomain("text", "robustband.audit/v1", ("csv", "jsonl"), workflow.load_paired,
    workflow.preview, workflow.analyze, workflow.verify_report,
    {"title": _labels("Paired text answers", "配对文本答案"), "fields": list(workflow.REQUIRED),
     "defaults": workflow.DEFAULT_FAMILY, "controls": text_controls, "example": workflow.DEMO_CSV, "example_format": "csv",
     "preview_fields": ["sample_id", "prompt", "gold", "output_a", "output_b"], "panel_id": "choices"}))

seg_controls = [{"key": "classes", "kind": "classes", "id": "segClasses", "title": _labels("Class indices: all, or comma-separated", "类别索引：all 或逗号分隔编号")},
                _checks("aggregations", _labels("IoU aggregation", "IoU 汇总"), segmentation.AGGREGATIONS, "segAgg"),
                _checks("empty_classes", _labels("Undefined class IoU", "类别 IoU 未定义时"), segmentation.EMPTY_CLASSES, "segEmpty")]
seg_controls[1]["options"][2]["requires"] = "group_available"
for option, names in zip(seg_controls[1]["options"] + seg_controls[2]["options"], [
        ("Pool pixel counts across records", "先汇总全部像素计数"), ("Equal image weights", "各图像等权"),
        ("Equal group weights after pooling", "组内汇总后各组等权"),
        ("Count an empty union as zero", "空并集记为零"), ("Omit empty unions", "忽略空并集（分母可能改变）")]):
    option["title"] = _labels(*names)
register_domain(AuditDomain("segmentation", "robustband.segmentation_audit/v1", ("jsonl",),
    lambda text, format: segmentation.load_confusions(text), segmentation.preview_confusions,
    segmentation.analyze_confusions, segmentation.verify_segmentation_report,
    {"title": _labels("Segmentation confusion counts", "语义分割混淆计数"), "fields": ["sample_id", "confusion_a", "confusion_b"],
     "defaults": {"classes": None, "aggregations": ["pooled", "image_mean"], "empty_classes": ["zero"]},
     "controls": seg_controls, "example": segmentation.DEMO_JSONL, "example_format": "jsonl",
     "note": _labels("Rows=true, columns=predicted; optional group and class_names. Choose one class target; do not mix overall mIoU with a rare-class objective.",
                     "行是真值类别，列是预测类别；可选 group 和 class_names。每次选择一个类别目标，分别审计总体 mIoU 和稀有类别指标。"),
     "preview_fields": ["sample_id", "group", "pixels"], "panel_id": "segSettings"}))

score_controls = [_checks("aggregations", _labels("Scalar aggregation", "数值汇总"), scores.AGGREGATIONS, "scoreAgg")]
score_controls[0]["options"][2]["requires"] = "group_available"
for option, names in zip(score_controls[0]["options"], [
        ("Equal sample weights", "各样本等权均值"), ("Compare model medians", "比较两个模型各自的中位数"),
        ("Equal group weights after within-group means", "组内平均后各组等权")]):
    option["title"] = _labels(*names)
register_domain(AuditDomain("scores", "robustband.scores_audit/v1", ("csv", "jsonl"), scores.load_scores,
    scores.preview_scores, scores.analyze_scores, scores.verify_scores_report,
    {"title": _labels("Recorded numeric metrics", "已记录的数值指标"), "fields": list(scores.REQUIRED),
     "defaults": scores.DEFAULT_FAMILY, "controls": score_controls, "example": scores.DEMO_CSV, "example_format": "csv",
     "note": _labels("Use one metric and unit throughout. direction=higher means higher is better; lower means lower is better. percent scores produce pp margins.",
                     "一次审计使用同一指标和单位。direction=higher 表示越高越好，lower 表示越低越好；percent 分数差值显示为百分点 pp。"),
     "preview_fields": ["sample_id", "score_a", "score_b", "group"], "panel_id": "scoreSettings"}))
