# SPDX-License-Identifier: MIT
"""Adoption decisions: objective tradeoffs, exact thresholds and strict imports."""
from copy import deepcopy
import json

import pytest
from robustband import decision as d
from robustband.cli import main
from robustband.domains import verify_audit
from robustband.report import render_html, save_report
from robustband.segmentation import DEMO_JSONL
from robustband.workflow import DEMO_CSV, DEFAULT_FAMILY
from test_local_ui_cli import request


def plan(domain="scores", threshold="0", operator="gt", unit="percent", direction="higher"):
    value = deepcopy(d.EXAMPLE_PLAN)
    value["domain"] = domain
    value["targets"] = value["targets"][:1]
    target = value["targets"][0]
    target.update(threshold=threshold, operator=operator)
    target.update(unit=unit, direction=direction)
    if domain == "text":
        target.pop("metric")
        target.pop("unit")
        target.pop("direction")
        target["family"] = deepcopy(DEFAULT_FAMILY)
    if domain == "segmentation":
        target.pop("metric")
        target.pop("unit")
        target.pop("direction")
        target["family"] = {"classes": [1], "aggregations": ["pooled", "image_mean"], "empty_classes": ["zero"]}
    return value


def test_realistic_tradeoff_wide_mapping_replay_and_escaped_report(tmp_path):
    p = deepcopy(d.EXAMPLE_PLAN)
    p["rationale"] = "<script>alert(1)</script>"
    report = d.analyze_decision(d.EXAMPLE, p, mapping=d.EXAMPLE_MAPPING, model_a="A<script>")
    assert report["result"] == {"status": "FAIL", "n_items": 3, "n_targets": 2, "target_tradeoff": True}
    assert [t["status"] for t in report["targets"]] == ["PASS", "FAIL"]
    assert report["targets"][0]["audit"]["result"]["exact_band"] == ["3", "3"]
    assert report["targets"][1]["audit"]["result"]["exact_band"] == ["-4/3", "-1"]
    assert report["targets"][1]["exact_slack_band"] == ["-5/6", "-1/2"]
    assert d.verify_decision(json.loads(json.dumps(report))) and verify_audit(report)
    html = render_html(report)
    assert "&lt;script&gt;" in html and "<script>" not in html and "objective tradeoff" in html
    save_report(report, tmp_path)
    assert json.loads((tmp_path/"report.json").read_text(encoding="utf-8")) == report
    assert "confidence intervals" in (tmp_path/"report.html").read_text(encoding="utf-8")


def test_exact_thresholds_ties_and_lower_is_better():
    text = 'sample_id,score_a,score_b,metric,unit,direction\na,9.9,10,mIoU,ms,lower\n'
    for threshold, operator, expected in (("0.1", "gt", "FAIL"), ("0.1", "ge", "PASS"),
            ("0.0999999999999999999999", "gt", "PASS"), ("0.1000000000000000000001", "ge", "FAIL")):
        r = d.analyze_decision(text, plan(threshold=threshold, operator=operator, unit="ms", direction="lower"))
        assert r["result"]["status"] == expected
        assert r["targets"][0]["unit"] == "ms"
        assert r["targets"][0]["audit"]["result"]["exact_band"] == ["1/10", "1/10"]
    # Difference of per-model medians, rather than the median paired difference.
    text = 'sample_id,score_a,score_b,metric,unit,direction\na,0,0,mIoU,n,higher\nb,0,10,mIoU,n,higher\nc,20,10,mIoU,n,higher\n'
    r = d.analyze_decision(text, plan(unit="n"))
    assert r["result"]["status"] == "FAIL"
    assert r["targets"][0]["audit"]["result"]["exact_band"] == ["-10", "0"]


def test_rule_sensitivity_is_separate_from_target_tradeoff():
    text = 'sample_id,score_a,score_b,metric,unit,direction\na,9,10,mIoU,ms,lower\nb,9,10,mIoU,ms,lower\nc,110,100,mIoU,ms,lower\n'
    r = d.analyze_decision(text, plan(unit="ms", direction="lower"))
    assert r["result"]["status"] == "REVIEW" and not r["result"]["target_tradeoff"]
    assert r["targets"][0]["failing_protocols"] == ["mean"]
    assert d.verify_decision(r)


def test_segmentation_thresholds_are_in_percentage_points_and_text_stays_original():
    r = d.analyze_decision(DEMO_JSONL, plan("segmentation", "1"), "jsonl")
    assert r["result"]["status"] == "REVIEW" and r["targets"][0]["exact_threshold"] == "1/100"
    counts = json.dumps(dict(sample_id="one", confusion_a=[[1,0],[0,1]], confusion_b=[[1,0],[1,0]]))
    for operator, status in (("gt", "FAIL"), ("ge", "PASS")):
        r = d.analyze_decision(counts, plan("segmentation", "100", operator), "jsonl")
        assert r["result"]["status"] == status and r["targets"][0]["display_margin_band"] == ["100", "100"]
        assert d.verify_decision(r)
    text = d.analyze_decision(DEMO_CSV, plan("text"), edition="professional")
    assert text["result"]["status"] == "REVIEW" and text["targets"][0]["unit"] == "score"
    assert verify_audit(text, "professional")


def test_long_format_alignment_exclusions_and_group_mapping():
    text = ('sample_id,score_a,score_b,metric,unit,direction,group\n'
            's1,3,1,mIoU,percent,higher,x\ns2,5,2,mIoU,percent,higher,y\n'
            's2,9,8,Human_IoU,percent,higher,y\ns1,8,8,Human_IoU,percent,higher,x\n'
            'other,1,0,unused,ms,lower,z\n')
    report = d.analyze_decision(text, d.EXAMPLE_PLAN)
    assert report["result"]["status"] == "PASS" and report["unselected_metrics"] == ["unused"]
    assert "unused" in render_html(report)
    # Pairing uses IDs, rather than record order, and never silently drops IDs.
    for bad in (text.replace('s2,9,8', 'different,9,8'), text.replace('higher,y\ns1,8', 'higher,x\ns1,8')):
        with pytest.raises(ValueError, match="same sample IDs"):
            d.analyze_decision(bad, d.EXAMPLE_PLAN)
    with pytest.raises(ValueError, match="missing from"):
        d.analyze_decision(text.replace('Human_IoU', 'renamed'), d.EXAMPLE_PLAN)
    mapping = deepcopy(d.EXAMPLE_MAPPING)
    mapping["group"] = "seed"
    p = plan()
    p["targets"][0]["family"] = {"aggregations": ["group_mean"]}
    r = d.analyze_decision(d.EXAMPLE, p, mapping=mapping)
    assert r["targets"][0]["audit"]["result"]["exact_band"] == ["3", "3"]
    assert d.preview_decision(d.EXAMPLE, mapping=mapping)["metrics"][0]["group_available"]


@pytest.mark.parametrize("change", [
    lambda p: p.clear(), lambda p: p.update(domain="other"), lambda p: p.update(name=""),
    lambda p: p.update(rationale="x"*2001), lambda p: p.update(targets=[]),
    lambda p: p["targets"].append(deepcopy(p["targets"][0])),
    lambda p: p["targets"][0].pop("reason"), lambda p: p["targets"][0].update(label=2),
    lambda p: p["targets"][0].update(role="unknown"), lambda p: p["targets"][0].update(operator="lt"),
    lambda p: p["targets"][0].update(threshold=0.1), lambda p: p["targets"][0].update(threshold="NaN"),
    lambda p: p["targets"][0].update(family=[]), lambda p: p["targets"][0].update(role="guardrail"),
    lambda p: p["targets"][0].update(direction="unknown"),
    lambda p: p["targets"][0].update(unit="fraction"), lambda p: p["targets"][0].update(direction="lower"),
])
def test_invalid_plans_are_rejected_before_deciding(change):
    p = plan()
    change(p)
    with pytest.raises(ValueError):
        d.analyze_decision(d.EXAMPLE, p, mapping=d.EXAMPLE_MAPPING)


@pytest.mark.parametrize("mapping", [
    {}, {**d.EXAMPLE_MAPPING, "sample_id": ""}, {**d.EXAMPLE_MAPPING, "group": 2},
    {**d.EXAMPLE_MAPPING, "metrics": []}, {**d.EXAMPLE_MAPPING, "metrics": [{}]},
    {**d.EXAMPLE_MAPPING, "metrics": [{**d.EXAMPLE_MAPPING["metrics"][0], "score_b": "overall_a"}]},
    {**d.EXAMPLE_MAPPING, "metrics": [d.EXAMPLE_MAPPING["metrics"][0]]*2},
    {**d.EXAMPLE_MAPPING, "sample_id": "missing"},
])
def test_ambiguous_mappings_fail(mapping):
    with pytest.raises(ValueError):
        d.preview_decision(d.EXAMPLE, mapping=mapping)


def test_inspection_format_limits_and_non_score_mapping(monkeypatch):
    assert d.inspect_columns(d.EXAMPLE)["columns"][0] == "seed"
    for text in ('', '[1]', '{"x":1}\n{"y":1}'):
        with pytest.raises(ValueError):
            d.inspect_columns(text, "jsonl")
    assert d.preview_decision(DEMO_JSONL, "segmentation", "jsonl")["n_items"] == 3
    for call in (lambda: d.preview_decision("", "segmentation", "csv"),
                 lambda: d.analyze_decision("", plan("segmentation")),
                 lambda: d.preview_decision(DEMO_CSV, "text", mapping={}),
                 lambda: d.analyze_decision(DEMO_CSV, plan("text"), mapping={}),
                 lambda: d.preview_decision('[1]', format="jsonl"),
                 lambda: d.preview_decision('', format="jsonl")):
        with pytest.raises(ValueError):
            call()
    monkeypatch.setattr(d, "MAX_ROWS", 3)
    with pytest.raises(ValueError, match="Mapped input exceeds"):
        d.preview_decision(d.EXAMPLE, mapping=d.EXAMPLE_MAPPING)


@pytest.mark.parametrize("change", [
    lambda r: r["input"]["mapping"]["metrics"][0].update(unit="fraction"),
    lambda r: r["plan"]["targets"][0].update(threshold="0.9"),
    lambda r: r["targets"][0].update(status="FAIL"),
    lambda r: r["source_sha256_lf"].update(**{"decision.py": "bad"}),
    lambda r: r["targets"][0]["audit"]["source_sha256_lf"].update(**{"scores.py": "bad"}),
])
def test_decision_replay_detects_altered_inputs_criteria_and_sources(change):
    r = d.analyze_decision(d.EXAMPLE, d.EXAMPLE_PLAN, mapping=d.EXAMPLE_MAPPING)
    change(r)
    with pytest.raises(ValueError, match="mismatch"):
        verify_audit(r)


def test_incomplete_decision_replay():
    for value in (None, {}, {"schema": d.SCHEMA}, {"schema": d.SCHEMA, "input": []}):
        with pytest.raises(ValueError):
            d.verify_decision(value)


def test_decision_http_routes_and_professional_isolation(server):
    assert request(server, "/decision")[0] == 200
    status, _, data = request(server, "/api/decision/example")
    example = json.loads(data)
    assert status == 200
    payload = dict(example, domain="scores")
    assert request(server, "/api/decision/columns", payload)[0] == 200
    assert request(server, "/api/decision/preview", payload)[0] == 200
    assert request(server, "/api/decision/plan", {"plan": example["plan"]})[0] == 200
    status, _, data = request(server, "/api/decision/audit", payload)
    assert status == 200 and verify_audit(json.loads(json.loads(data)["json"]))
    assert request(server, "/api/decision/audit", payload, {"X-Robustband-Token": "bad"})[0] == 403
    server.edition = "professional"
    assert request(server, "/api/decision/audit", payload)[0] == 400
    status, _, data = request(server, "/api/decision/example")
    example = json.loads(data)
    assert status == 200 and example["plan"]["domain"] == "text"
    assert request(server, "/api/decision/audit", example)[0] == 200


def test_decision_cli_exit_codes_templates_and_replay(tmp_path, capsys):
    assert main(["decision-template", str(tmp_path)]) == 0
    args = ["decision", str(tmp_path/"paired.csv"), "--plan", str(tmp_path/"plan.json"),
            "--mapping", str(tmp_path/"mapping.json"), "--output", str(tmp_path/"report")]
    assert main(args+["--require-pass"]) == 1
    assert main(args) == 0
    assert main(["verify", str(tmp_path/"report/report.json")]) == 0
    p = plan(threshold="1")
    (tmp_path/"plan.json").write_text(json.dumps(p), encoding="utf-8")
    assert main(args+["--require-pass"]) == 0
    standard = 'sample_id,score_a,score_b,metric,unit,direction\na,3,1,mIoU,percent,higher\n'
    (tmp_path/"paired.csv").write_text(standard, encoding="utf-8")
    without_mapping = args[:4]+args[6:]
    assert main(without_mapping+["--require-pass"]) == 0
    assert main(["--edition", "professional", "decision-template", str(tmp_path)]) == 2
    with pytest.raises(SystemExit) as invalid_flag:
        main(args+["--require-robust"])
    assert invalid_flag.value.code == 2
    assert "FAIL" in capsys.readouterr().out
