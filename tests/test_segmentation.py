# SPDX-License-Identifier: MIT
"""Exact aggregation changes, absent classes, pairing integrity and replay."""
from copy import deepcopy
import json

import pytest
from robustband import segmentation as sg
from robustband import audit_engine
from robustband.cli import main
from robustband.report import render_html


FAMILY = {"classes": [1], "aggregations": ["pooled", "image_mean", "group_mean"], "empty_classes": ["zero", "omit"]}


def test_hand_checkable_aggregation_reversal_and_exact_replay(tmp_path):
    rows = sg.load_confusions("\ufeff\n" + sg.DEMO_JSONL)
    report = sg.analyze_confusions(rows, FAMILY)
    assert report["result"]["exact_band"] == ["-49/51", "1/3"]
    assert report["result"]["verdict"] == "UNIDENTIFIABLE" and report["result"]["strict_sign_flip"]
    assert report["result"]["tie_count"] == 2 and report["result"]["support_count"] == 2
    assert report["result"]["distinct_score_pairs"] == 3
    assert sg.verify_segmentation_report(json.loads(json.dumps(report)))
    assert "-96.078431 pp" in render_html(report) and "Selected class diagnostics" in render_html(report)
    rows[0]["confusion_a"][0][0] = 0
    assert report["inputs"][0]["confusion_a"][0][0] == 9
    assert sg.preview_confusions(sg.DEMO_ROWS)["group_available"]
    assert sg.analyze_confusions(sg.DEMO_ROWS)["family"]["classes"] == [0, 1]


@pytest.mark.parametrize("change,match", [
    (lambda r: r[0].pop("sample_id"), "needs"),
    (lambda r: r[0].update(sample_id=True), "sample_id"),
    (lambda r: r[1].update(sample_id="small-1"), "duplicate"),
    (lambda r: r[0].update(confusion_a=[]), "square"),
    (lambda r: r[0].update(confusion_a=[[1, 2], [3]]), "square"),
    (lambda r: r[0]["confusion_a"][0].__setitem__(0, -1), "integer counts"),
    (lambda r: r[0]["confusion_a"][0].__setitem__(0, 1.0), "integer counts"),
    (lambda r: r[0]["confusion_a"][0].__setitem__(0, True), "integer counts"),
    (lambda r: r[0]["confusion_a"][0].__setitem__(0, 2**63), "integer counts"),
    (lambda r: r[0].update(confusion_b=[[1, 0, 0], [0, 1, 0], [0, 0, 1]]), "dimension"),
    (lambda r: r[0]["confusion_b"][0].__setitem__(0, 8), "ground-truth"),
    (lambda r: r[0].update(group=2), "string label"),
    (lambda r: r[0].update(class_names=["one"]), "class_names"),
    (lambda r: r[0].update(class_names=["one", "one"]), "class_names"),
    (lambda r: r[0].update(class_names=["one", "two"]), "order"),
])
def test_invalid_matrices_and_metadata(change, match):
    rows = deepcopy(sg.DEMO_ROWS)
    change(rows)
    with pytest.raises(ValueError, match=match):
        sg.analyze_confusions(rows)


def test_input_errors_empty_and_limits(monkeypatch):
    for text, match in ((None, "UTF-8"), ("broken", "line 1"), ("{\"x\":NaN}", "constant"),
                        ("{\"x\":1,\"x\":2}", "Duplicate"), ("\n", "no paired")):
        with pytest.raises(ValueError, match=match):
            sg.load_confusions(text)
    monkeypatch.setattr(sg, "MAX_BYTES", 1)
    with pytest.raises(ValueError, match="4 MiB"):
        sg.load_confusions(sg.DEMO_JSONL)
    monkeypatch.setattr(sg, "MAX_BYTES", 10000)
    monkeypatch.setattr(sg, "MAX_ROWS", 1)
    for call in (lambda: sg.load_confusions(sg.DEMO_JSONL), lambda: sg.analyze_confusions(sg.DEMO_ROWS)):
        with pytest.raises(ValueError, match="at most 1"):
            call()


@pytest.mark.parametrize("family", [
    {}, [], {**FAMILY, "classes": []}, {**FAMILY, "classes": [True]},
    {**FAMILY, "classes": [2]}, {**FAMILY, "classes": [1, 1]},
    {**FAMILY, "aggregations": []}, {**FAMILY, "aggregations": ["invented"]},
    {**FAMILY, "empty_classes": ["zero", "zero"]},
])
def test_policy_declaration(family):
    with pytest.raises(ValueError):
        sg.analyze_confusions(sg.DEMO_ROWS, family)


def test_model_names_missing_groups_and_fraction_size(monkeypatch):
    with pytest.raises(ValueError, match="distinct"):
        sg.analyze_confusions(sg.DEMO_ROWS, model_a="B", model_b="B")
    rows = deepcopy(sg.DEMO_ROWS)
    rows[0]["group"] = ""
    with pytest.raises(ValueError, match="group_mean"):
        sg.analyze_confusions(rows, FAMILY)
    assert not sg.preview_confusions(rows)["group_available"]
    monkeypatch.setattr(audit_engine, "MAX_EXACT_BITS", 1)
    with pytest.raises(ValueError, match="fraction is too large"):
        sg.analyze_confusions(sg.DEMO_ROWS)


def test_absent_classes_and_zero_true_positive_diagnostics():
    absent = {"sample_id": "none", "confusion_a": [[10, 0], [0, 0]], "confusion_b": [[10, 0], [0, 0]]}
    zero = sg.analyze_confusions([absent], {"classes": [1], "aggregations": ["pooled"], "empty_classes": ["zero"]})
    assert zero["result"]["verdict"] == "REFUTED" and "undefined class-units" in zero["warnings"][0]
    with pytest.raises(ValueError, match="undefined in every unit"):
        sg.analyze_confusions([absent], {"classes": [1], "aggregations": ["image_mean"], "empty_classes": ["omit"]})
    wrong = {"sample_id": "wrong", "confusion_a": [[9, 0], [1, 0]], "confusion_b": [[9, 0], [1, 0]]}
    result = sg.analyze_confusions([wrong], {"classes": [1], "aggregations": ["pooled"], "empty_classes": ["zero"]})
    assert any("both sides" in warning for warning in result["warnings"])
    better = deepcopy(wrong); better["confusion_a"] = [[9, 0], [0, 1]]
    assert sg.analyze_confusions([better], {"classes": [1], "aggregations": ["pooled"], "empty_classes": ["zero"]})["result"]["verdict"] == "ROBUST"


@pytest.mark.parametrize("change", [
    lambda r: r["result"].update(exact_band=["0", "0"]),
    lambda r: r["family"].update(classes=[0]),
    lambda r: r["source_sha256_lf"].update(**{"segmentation.py": "bad"}),
    lambda r: r["configurations"][0].update(display_margin="0 pp"),
])
def test_replay_rejects_tampering(change):
    report = sg.analyze_confusions(sg.DEMO_ROWS)
    change(report)
    with pytest.raises(ValueError, match="mismatch"):
        sg.verify_segmentation_report(report)


def test_replay_schema_and_cli(tmp_path):
    for value in ({}, None):
        with pytest.raises(ValueError, match="schema"):
            sg.verify_segmentation_report(value)
    with pytest.raises(ValueError, match="Incomplete"):
        sg.verify_segmentation_report({"schema": "robustband.segmentation_audit/v1"})
    path = tmp_path / "confusions.jsonl"
    path.write_text(sg.DEMO_JSONL, encoding="utf-8")
    output = tmp_path / "report"
    assert main(["segment", str(path), "--classes", "1", "--output", str(output), "--require-robust"]) == 1
    assert main(["verify", str(output / "report.json")]) == 0
    data = json.loads((output / "report.json").read_text())
    assert data["result"]["exact_band"] == ["-49/51", "1/3"]
