# SPDX-License-Identifier: MIT
"""User input integrity, exact decisions, report escaping and replay failures."""
from copy import deepcopy
import json

import pytest
import robustband as rb
from robustband import workflow as wf
from robustband.report import render_html, save_report


def record(**changes):
    result = {"sample_id": "one", "prompt": "What is 6 times 7?", "gold": "42",
              "output_a": "7 then 42", "output_b": "42 then 7"}
    result.update(changes)
    return result


def test_csv_jsonl_and_bom_preserve_outputs_and_exact_decisions(tmp_path):
    rows = wf.load_paired("\ufeff" + wf.DEMO_CSV)
    assert rows[0]["output_a"] == "the answer is 7 but really 42"
    assert wf.load_paired("\n" + json.dumps(rows[0]) + "\n", "jsonl") == rows
    report = wf.analyze(rows, model_a="A<script>", model_b="B&co")
    assert report["result"]["exact_band"] == ["-1", "1"]
    assert report["result"]["support_fraction"] == "1/2"
    assert report["result"]["strict_sign_flip"] is True
    assert report["witnesses"]["minimum"]["protocol"] == "first_num|exact_match|micro"
    assert wf.verify_report(report)
    directory = save_report(report, tmp_path / "nested")
    html = (directory / "report.html").read_text(encoding="utf-8")
    assert "A&lt;script&gt;" in html and "B&amp;co" in html and "A<script>" not in html
    assert wf.verify_report(json.loads((directory / "report.json").read_text(encoding="utf-8")))


@pytest.mark.parametrize("text,format,match", [
    ("", "csv", "header"), ("sample_id,sample_id,prompt,gold,output_a,output_b\n", "csv", "duplicate"),
    (wf.DEMO_CSV + "x,y,42,a,b,extra\n", "csv", "number of fields"),
    (wf.DEMO_CSV + "x,y,42,a\n", "csv", "number of fields"),
    ("sample_id,prompt,gold,output_a,output_b\nx,y,42,\"unclosed", "csv", "Invalid CSV"),
    ("broken", "jsonl", "line 1"), ("{\"x\":NaN}", "jsonl", "constant"),
    ("{\"sample_id\":1,\"sample_id\":2}", "jsonl", "Duplicate JSON"),
    ("\n", "jsonl", "no paired"), ("{}", "other", "input format"),
    (None, "csv", "UTF-8"), ("x" * (wf.MAX_BYTES + 1), "csv", "4 MiB"),
], ids=["empty-csv", "duplicate-header", "excess-fields", "missing-fields", "malformed-csv",
        "invalid-json", "nan-json", "duplicate-json", "empty-json", "format", "nontext", "oversized"])
def test_invalid_files_are_rejected(text, format, match):
    with pytest.raises(ValueError, match=match):
        wf.load_paired(text, format)


@pytest.mark.parametrize("rows,match", [
    ([None], "needs fields"), ([{}], "needs fields"), ([record(sample_id=True)], "sample_id"),
    ([record(sample_id=" ")], "sample_id"), ([record(sample_id=1), record(sample_id="1")], "duplicate"),
    ([record(prompt="")], "prompt"), ([record(gold=" ")], "gold"),
    ([record(output_a=2)], "output_a"), ([record(output_b=None)], "output_b"),
    ([record(**{"class": []})], "class"),
])
def test_record_schema_and_duplicate_identity(rows, match):
    with pytest.raises(ValueError, match=match):
        wf.analyze(rows)


def test_row_limits_apply_to_both_formats_and_replay(monkeypatch):
    monkeypatch.setattr(wf, "MAX_ROWS", 1)
    rows = [record(), record(sample_id="two")]
    for invoke in (lambda: wf.analyze(rows),
                   lambda: wf.load_paired(wf.DEMO_CSV + "two,q,42,42,7\n"),
                   lambda: wf.load_paired("\n".join(json.dumps(r) for r in rows), "jsonl")):
        with pytest.raises(ValueError, match="at most 1"):
            invoke()


@pytest.mark.parametrize("family,match", [
    ([], "Declare"), ({}, "Declare"),
    ({"parses": [], "metrics": ["exact_match"], "aggs": ["micro"]}, "parses"),
    ({"parses": ["last_num"], "metrics": ["invented"], "aggs": ["micro"]}, "metrics"),
    ({"parses": ["last_num"], "metrics": ["exact_match"], "aggs": ["micro", "micro"]}, "Duplicate"),
])
def test_explicit_family_validation(family, match):
    with pytest.raises(ValueError, match=match):
        wf.analyze([record()], family)


@pytest.mark.parametrize("a,b", [("", "B"), ("A", "A"), (None, "B"), ("A", " ")])
def test_model_names(a, b):
    with pytest.raises(ValueError, match="distinct"):
        wf.analyze([record()], model_a=a, model_b=b)


def test_grouping_requires_complete_metadata_and_matches_frozen_engine():
    settings = {"parses": ["first_num", "last_num"], "metrics": list(rb.METRIC), "aggs": list(rb.AGG)}
    with pytest.raises(ValueError, match="class field"):
        wf.analyze([record()], settings)
    rows = [record(**{"class": "algebra", "len_bucket": 2}),
            record(sample_id=2, output_a="42", output_b="wrong", **{"class": "arithmetic", "len_bucket": 1})]
    report = wf.analyze(rows, settings)
    normalized = report["inputs"]
    preds = {model: {"items": [(r[side], r["gold"], {k: r[k] for k in ("class", "len_bucket")}) for r in normalized]}
             for model, side in (("A", "output_a"), ("B", "output_b"))}
    exact = rb.rational.rational_band(preds["A"]["items"], preds["B"]["items"], rb.build_family(**settings))
    assert report["result"]["exact_band"] == [str(exact["lo"]), str(exact["hi"])]
    assert {c["protocol"]: c["margin"] for c in report["configurations"]} == {k: str(m) for k, m, certain in exact["rows"]}
    settings["parses"].clear()
    assert report["family"]["parses"] == ["first_num", "last_num"]


def test_robust_refuted_tied_and_empty_output_diagnostics():
    family = {"parses": ["last_num"], "metrics": ["exact_match"], "aggs": ["micro"]}
    robust = wf.analyze([record(output_a="42", output_b="7")], family)
    assert robust["result"]["verdict"] == "ROBUST" and robust["result"]["exact_band"] == ["1", "1"]
    refuted = wf.analyze([record(output_a="7", output_b="42")], family)
    assert refuted["result"]["verdict"] == "REFUTED" and refuted["result"]["reverse_count"] == 1
    tie = wf.analyze([record(output_a="", output_b="")], family)
    assert tie["result"]["verdict"] == "REFUTED" and tie["result"]["tie_count"] == 1
    assert tie["configurations"][0]["all_zero"] and len(tie["warnings"]) == 2
    assert "Ties do not establish" in render_html(tie)
    tie["limits"].clear()
    assert wf.analyze([record()], family)["limits"]


@pytest.mark.parametrize("change", [
    lambda r: r["result"].update(exact_band=["0", "1"]),
    lambda r: r["inputs"][0].update(output_a="42"),
    lambda r: r["family"].update(parses=["last_num"]),
    lambda r: r.update(software_version="old"),
    lambda r: r["source_sha256_lf"].update(**{"workflow.py": "0" * 64}),
])
def test_report_tampering_fails_recomputation(change):
    report = deepcopy(wf.analyze([record()]))
    change(report)
    with pytest.raises(ValueError, match="mismatch"):
        wf.verify_report(report)


def test_report_schema_and_missing_fields():
    for value in (None, {}, {"schema": "different"}):
        with pytest.raises(ValueError, match="schema"):
            wf.verify_report(value)
    with pytest.raises(ValueError, match="Incomplete"):
        wf.verify_report({"schema": "robustband.audit/v1"})
