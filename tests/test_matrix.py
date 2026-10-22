# SPDX-License-Identifier: MIT
"""Ranking audits: shared samples, exact ranks, pair flips and replay."""
import json

import pytest

from robustband import matrix as mx
from robustband.cli import main
from robustband.domains import verify_audit
from robustband.report import render_html, save_report

FLIP_CSV = (",".join(mx.REQUIRED) + "\n"
            "q1,cot,42,the answer is 7 but really 42\n"
            "q1,plain,42,42 no wait 7\n"
            "q1,exact,42,42\n")
STABLE_CSV = (",".join(mx.REQUIRED) + "\n"
              "q1,a,42,42\nq1,b,42,7\n"
              "q2,a,42,42\nq2,b,42,7\n")


def test_ranking_flip_is_hand_checkable_and_replayable():
    models, samples, rows, _ = mx.load_long(FLIP_CSV)
    assert models == ["cot", "plain", "exact"] and samples == ["q1"]
    report = mx.analyze_matrix(rows)
    result = report["result"]
    assert result["verdict"] == "SENSITIVE" and result["n_models"] == 3 and result["n_protocols"] == 2
    assert result["first_place_counts"] == {"cot": 1, "plain": 1, "exact": 2}
    assert result["rank_floor"] == {"cot": 1, "plain": 1, "exact": 1}
    assert result["rank_ceiling"] == {"cot": 3, "plain": 3, "exact": 1}
    assert result["flipping_pairs"] == 1 and result["n_reaching_first"] == 3
    pairs = {frozenset((p["model_a"], p["model_b"])): p for p in report["pairs"]}
    assert pairs[frozenset(("cot", "plain"))]["exact_band"] == ["-1", "1"]
    assert pairs[frozenset(("cot", "plain"))]["flips"] is True
    assert pairs[frozenset(("cot", "exact"))]["exact_band"] == ["-1", "0"]   # tie is not a flip
    assert pairs[frozenset(("cot", "exact"))]["verdict"] == "REFUTED"
    assert mx.verify_matrix_report(json.loads(json.dumps(report)))
    assert verify_audit(json.loads(json.dumps(report)))
    html = render_html(report)
    assert "名次会不会因为评分规则而改变" in html and "SENSITIVE" in html
    assert "翻转 / flips [-1, 1]" in html


def test_stable_ranking_and_model_subset():
    rows = mx.load_long(STABLE_CSV)[2]
    report = mx.analyze_matrix(rows)
    assert report["result"]["verdict"] == "STABLE" and report["result"]["flipping_pairs"] == 0
    assert report["result"]["first_place_counts"] == {"a": 2, "b": 0}
    with pytest.raises(ValueError, match="at least two distinct models"):
        mx.analyze_matrix(rows, models=["a"])
    with pytest.raises(ValueError, match="at least two distinct models"):
        mx.analyze_matrix(rows, models=["a", "missing"])


def test_a_stable_leader_with_moving_order_is_reported_separately():
    rows_list = []
    for index in range(1, 6):
        rows_list.append({"sample_id": "s%d" % index, "model": "best", "gold": "42", "output": "42"})
    for index in range(1, 4):                                  # a wins under first_num, b under last_num
        rows_list.append({"sample_id": "s%d" % index, "model": "a", "gold": "42", "output": "42 0"})
        rows_list.append({"sample_id": "s%d" % index, "model": "b", "gold": "42", "output": "0 42"})
    for index in (4, 5):
        rows_list.append({"sample_id": "s%d" % index, "model": "a", "gold": "42", "output": "0 0"})
        rows_list.append({"sample_id": "s%d" % index, "model": "b", "gold": "42", "output": "0 0"})
    report = mx.analyze_matrix(rows_list)
    assert report["result"]["verdict"] == "LEADER-STABLE"
    assert report["result"]["first_place_counts"] == {"best": 2, "a": 0, "b": 0}
    assert report["result"]["rank_ceiling"] == {"best": 1, "a": 3, "b": 3}
    assert report["result"]["rank_floor"] == {"best": 1, "a": 2, "b": 2}
    html = render_html(report)
    assert "第一名稳定" in html and "领先 / ahead" in html


def test_jsonl_input_and_preview():
    text = "".join(json.dumps({"sample_id": row["sample_id"], "model": row["model"],
                               "gold": row["gold"], "output": row["output"]}) + "\n"
                   for row in mx.load_long(FLIP_CSV)[2])
    models, samples, rows, _ = mx.load_long(text, "jsonl")
    assert models == ["cot", "plain", "exact"] and len(rows) == 3
    preview = mx.preview_matrix(rows)
    assert preview["n_models"] == 3 and preview["empty_outputs"] == {"cot": 0, "plain": 0, "exact": 0}


def test_group_protocols_need_consistent_labels():
    text = (",".join(mx.REQUIRED + ("class",)) + "\n"
            "q1,a,42,42,x\nq1,b,42,7,x\n")
    rows = mx.load_long(text)[2]
    report = mx.analyze_matrix(rows, {"parses": ["first_num"], "metrics": ["exact_match"], "aggs": ["macro_class"]})
    assert report["protocols"][0]["ranks"] == {"a": 1, "b": 2}
    broken = text.replace("q1,b,42,7,x", "q1,b,42,7,y")
    with pytest.raises(ValueError, match="inconsistent class"):
        mx.load_long(broken)
    blank = text.replace(",x\n", ",\n").replace("q1,b,42,7,x", "q1,b,42,7,")
    with pytest.raises(ValueError, match="requires a nonempty class"):
        mx.analyze_matrix(mx.load_long(blank)[2],
                          {"parses": ["first_num"], "metrics": ["exact_match"], "aggs": ["macro_class"]})


@pytest.mark.parametrize("text,match", [
    ("", "CSV header needs"),
    ("sample_id,model,gold\nq1,a,42\n", "CSV header needs"),
    (",".join(mx.REQUIRED) + "\nq1,a,42,42\n", "at least two models"),
    (",".join(mx.REQUIRED) + "\nq1,a,42,42\nq1,b,42\n", "different number of fields"),
    (",".join(mx.REQUIRED) + "\nq1,a,42,42\nq1,a,42,42\n", "repeats sample"),
    (",".join(mx.REQUIRED) + "\nq1,a,42,42\nq1,b,43,42\n", "different reference answers"),
    (",".join(mx.REQUIRED) + "\nq1,a,42,42\nq2,b,42,42\n", "missing models"),
    (",".join(mx.REQUIRED) + "\nq1,a,42\nq1,b,42,42\n", "different number of fields"),
    (",".join(mx.REQUIRED) + "\nq1,a,,42\nq1,b,,42\n", "gold must be a nonempty"),
], ids=["empty", "missing-columns", "one-model", "short-row", "duplicate", "gold-mismatch",
        "missing-model-sample", "short-record", "empty-gold"])
def test_invalid_long_tables(text, match):
    with pytest.raises(ValueError, match=match):
        mx.load_long(text)


def test_validation_limits_and_verifier_failures():
    with pytest.raises(ValueError, match="at most 8 models"):
        rows = [{"sample_id": "q", "model": "m%d" % index, "gold": "42", "output": "42"} for index in range(9)]
        mx.analyze_matrix(rows)
    with pytest.raises(ValueError, match="Declare parses"):
        mx.analyze_matrix(mx.load_long(STABLE_CSV)[2], {"parses": ["first_num"]})
    with pytest.raises(ValueError, match="supported option"):
        mx.analyze_matrix(mx.load_long(STABLE_CSV)[2], {"parses": ["nope"], "metrics": ["exact_match"], "aggs": ["micro"]})
    with pytest.raises(ValueError, match="Duplicate protocol option"):
        mx.analyze_matrix(mx.load_long(STABLE_CSV)[2],
                          {"parses": ["first_num", "first_num"], "metrics": ["exact_match"], "aggs": ["micro"]})
    for value in (None, {}, {"schema": "other"}):
        with pytest.raises(ValueError, match="schema"):
            mx.verify_matrix_report(value)
    with pytest.raises(ValueError, match="Incomplete"):
        mx.verify_matrix_report({"schema": mx.SCHEMA})
    report = mx.analyze_matrix(mx.load_long(STABLE_CSV)[2])
    broken = json.loads(json.dumps(report))
    broken["result"]["verdict"] = "SENSITIVE"
    with pytest.raises(ValueError, match="Report mismatch"):
        mx.verify_matrix_report(broken)


def test_matrix_cli_writes_reports_and_gates_on_stability(tmp_path):
    flip = tmp_path / "flip.csv"
    flip.write_text(FLIP_CSV, encoding="utf-8")
    output = tmp_path / "flip-report"
    assert main(["matrix", str(flip), "--output", str(output), "--require-stable"]) == 1
    stored = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert stored["result"]["verdict"] == "SENSITIVE"
    assert "ranking audit" in (output / "report.html").read_text(encoding="utf-8")
    assert main(["verify", str(output / "report.json")]) == 0
    stable = tmp_path / "stable.csv"
    stable.write_text(STABLE_CSV, encoding="utf-8")
    assert main(["matrix", str(stable), "--output", str(tmp_path / "stable-report"), "--require-stable"]) == 0
    assert main(["matrix", str(stable), "--models", "a", "--output", str(tmp_path / "bad")]) == 2


def test_pair_labels_cover_ahead_behind_ties_and_flips():
    behind = (",".join(mx.REQUIRED) + "\n"
              "q1,weak,42,7\nq1,strong,42,42\n")
    html = render_html(mx.analyze_matrix(mx.load_long(behind)[2]))
    assert "落后 / behind [-1, -1]" in html
    tied = (",".join(mx.REQUIRED) + "\n"
            "q1,a,42,7\nq1,b,42,7\n")
    html = render_html(mx.analyze_matrix(mx.load_long(tied)[2]))
    assert "含并列 / ties [0, 0]" in html


def test_matrix_report_escapes_model_names(tmp_path):
    text = FLIP_CSV.replace("cot", "<script>")
    report = mx.analyze_matrix(mx.load_long(text)[2])
    html = render_html(report)
    assert "&lt;script&gt;" in html and "<script>" not in html
    directory = save_report(report, tmp_path / "escaped")
    assert json.loads((directory / "report.json").read_text(encoding="utf-8")) == report


def test_row_level_validation_and_warnings(monkeypatch):
    good = {"sample_id": "q1", "model": "a", "gold": "42", "output": "42"}
    other = {"sample_id": "q1", "model": "b", "gold": "42", "output": "42"}
    cases = [
        ([{k: v for k, v in good.items() if k != "output"}, other], "needs fields"),
        ([dict(good, sample_id="  "), other], "nonempty sample_id"),
        ([dict(good, model="  "), other], "nonempty model name"),
        ([dict(good, output=7), other], "output must be a string"),
        ([dict(good, **{"class": None}), dict(other, **{"class": None})], "string or integer"),
    ]
    for rows, match in cases:
        with pytest.raises(ValueError, match=match):
            mx.analyze_matrix(rows)
    with pytest.raises(ValueError, match="no measurement rows"):
        mx.analyze_matrix([])
    monkeypatch.setattr(mx, "MAX_ROWS", 1)
    with pytest.raises(ValueError, match="at most 1 measurement rows"):
        mx.analyze_matrix([good, other])
    monkeypatch.undo()
    # every model scoring zero is reported, and empty outputs stay in the audit
    zeros = [dict(good, output="x"), dict(other, output="x")]
    report = mx.analyze_matrix(zeros)
    assert any("scores every model zero" in warning for warning in report["warnings"])
    empty = [dict(good, output=""), other]
    report = mx.analyze_matrix(empty)
    assert any("has 1 empty outputs" in warning for warning in report["warnings"])
    assert report["pairs"] and report["result"]["n_models"] == 2
