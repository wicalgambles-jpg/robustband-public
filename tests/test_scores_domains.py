# SPDX-License-Identifier: MIT
"""Cross-domain contracts, oriented measurements and lossless decimal ingestion."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction as F
import json

import pytest
from robustband import scores as sc, domains as dm, workflow as wf
from robustband.cli import main
from robustband.report import render_html


def record(**changes):
    row = dict(sample_id="one", score_a="0.1", score_b="0.2", metric="error", unit="fraction", direction="lower")
    row.update(changes)
    return row


def test_decimal_ingestion_oriented_margins_and_medians():
    report = sc.analyze_scores(sc.load_scores("\ufeff" + sc.DEMO_CSV), {"aggregations": list(sc.AGGREGATIONS)})
    assert report["result"]["exact_band"] == ["-9/2", "1"]
    assert report["result"]["verdict"] == "UNIDENTIFIABLE" and report["result"]["support_fraction"] == "1/3"
    assert report["configurations"][0]["margin"] == "-8/3"
    assert report["configurations"][1]["margin"] == "1"
    assert "A &lt; B" in render_html(report) and "B-A" in render_html(report)
    assert sc.verify_scores_report(json.loads(json.dumps(report)))
    row = record(score_a="0.1000000000000000000001", score_b=Decimal("0.1"), direction="higher")
    exact = sc.analyze_scores([row])
    assert exact["result"]["exact_band"] == [str(F(1, 10**22))]*2
    assert exact["result"]["verdict"] == "ROBUST" and exact["warnings"]
    jsonl = '{"sample_id":"one","score_a":9007199254740993.0,"score_b":9007199254740992,"metric":"count","unit":"n","direction":"higher"}'
    assert sc.analyze_scores(sc.load_scores("\n"+jsonl+"\n", "jsonl"))["result"]["exact_band"] == ["1", "1"]
    tie = sc.analyze_scores([record(score_a=0, score_b=0)])
    assert tie["result"]["verdict"] == "REFUTED" and tie["result"]["tie_count"] == 2
    assert tie["configurations"][0]["all_zero"]
    even = sc.analyze_scores([record(score_a=1, score_b=0), record(sample_id=2, score_a=2, score_b=0)], {"aggregations": ["median"]})
    assert even["configurations"][0]["score_a"] == "3/2"
    row["score_a"] = "2"
    assert exact["inputs"][0]["score_a"] == "0.1000000000000000000001"


@pytest.mark.parametrize("rows,match", [
    ([], "no paired"), ([{}], "needs fields"), ([record(sample_id=True)], "sample_id"),
    ([record(), record()], "duplicate"), ([record(metric="")], "nonempty"),
    ([record(direction="maximize")], "higher or lower"), ([record(), record(sample_id=2, unit="percent")], "mix"),
    ([record(group=2)], "string label"), ([record(score_a=0.1)], "binary floats"),
    ([record(score_a="NaN")], "finite"), ([record(score_a="1_0")], "finite"),
    ([record(score_a="1e129")], "limits"), ([record(score_a="1"*257)], "limits"),
    ([record(score_a="1"*513)], "finite"), ([record(score_a="1e9999999999999999999999999999999")], "Invalid decimal"),
])
def test_bad_numeric_records(rows, match):
    with pytest.raises(ValueError, match=match):
        sc.analyze_scores(rows)


@pytest.mark.parametrize("text,format,match", [
    (None,"csv","UTF-8"), ("", "csv", "header"),
    ("sample_id,score_a,score_b,metric,unit,direction,sample_id\n", "csv", "duplicate"),
    (sc.DEMO_CSV+"x,1,2,error,ms,lower\n", "csv", "number of fields"),
    (sc.DEMO_CSV+'x,"unclosed', "csv", "Invalid CSV"), ("broken", "jsonl", "line 1"),
    ('{"x":NaN}', "jsonl", "constant"), ('{"x":1,"x":2}', "jsonl", "Duplicate"),
    ("", "jsonl", "no paired"), ("", "unknown", "format"),
])
def test_bad_score_files(text, format, match):
    with pytest.raises(ValueError, match=match):
        sc.load_scores(text, format)


def test_limits_groups_and_policy_errors(monkeypatch):
    monkeypatch.setattr(sc, "MAX_BYTES", 1)
    with pytest.raises(ValueError, match="4 MiB"):
        sc.load_scores(sc.DEMO_CSV)
    monkeypatch.setattr(sc, "MAX_BYTES", 10000)
    monkeypatch.setattr(sc, "MAX_ROWS", 1)
    for call in (lambda: sc.load_scores(sc.DEMO_CSV), lambda: sc.load_scores("\n".join(json.dumps(record(sample_id=i)) for i in range(2)), "jsonl"),
                 lambda: sc.analyze_scores([record(), record(sample_id=2)])):
        with pytest.raises(ValueError, match="at most 1"):
            call()
    for family in ({}, [], {"aggregations": []}, {"aggregations": ["mean", "mean"]}, {"aggregations": ["invented"]}):
        with pytest.raises(ValueError):
            sc.analyze_scores([record()], family)
    with pytest.raises(ValueError, match="group_mean"):
        sc.analyze_scores([record()], {"aggregations": ["group_mean"]})
    assert not sc.preview_scores([record()])["group_available"]


@pytest.mark.parametrize("change", [
    lambda r: r["inputs"][0].update(direction="higher"),
    lambda r: r["measurement"].update(unit="percent"),
    lambda r: r["source_sha256_lf"].update(**{"audit_engine.py":"bad"}),
    lambda r: r["result"].update(display_band=["0", "0"]),
])
def test_score_replay_rejects_changed_meaning_and_sources(change):
    report = sc.analyze_scores([record()])
    change(report)
    with pytest.raises(ValueError, match="mismatch"):
        sc.verify_scores_report(report)


def test_score_schema_errors():
    for report in (None, {}):
        with pytest.raises(ValueError, match="schema"):
            sc.verify_scores_report(report)
    with pytest.raises(ValueError, match="Incomplete"):
        sc.verify_scores_report({"schema":"robustband.scores_audit/v1"})


def test_all_builtin_domain_contracts():
    assert len(dm.domain_options()) == 3
    for option in dm.domain_options():
        report = dm.audit_domain(option["id"], option["example"], option["example_format"])
        assert dm.verify_audit(report)
        assert dm.preview_domain(option["id"], option["example"])["n_items"] >= 1
        assert "audit_engine.py" in report["source_sha256_lf"]
    options = dm.domain_options()
    options[0]["defaults"]["parses"].clear()
    dm.get_domain("text").metadata["defaults"]["parses"].clear()
    assert dm.get_domain("text").metadata["defaults"]["parses"] == wf.DEFAULT_FAMILY["parses"]
    for id in (None, [], "unknown"):
        with pytest.raises(ValueError, match="Unknown audit domain"):
            dm.get_domain(id)
    with pytest.raises(ValueError, match="supports input formats"):
        dm.load_domain("segmentation", "", "csv")
    for report in (None, {}, {"schema":"unknown"}):
        with pytest.raises(ValueError, match="schema"):
            dm.verify_audit(report)


def test_trusted_adapter_registration_and_replay_dispatch(monkeypatch):
    monkeypatch.setattr(dm, "_DOMAINS", dict(dm._DOMAINS))
    original = dm.get_domain("scores")
    schema = "example.latency_audit/v1"
    def analyze(*args):
        report = sc.analyze_scores(*args)
        report["schema"] = schema
        return report
    def verify(report):
        clone = deepcopy(report)
        clone["schema"] = original.schema
        return sc.verify_scores_report(clone)
    adapter = replace(original, id="latency_example", schema=schema, analyze=analyze, verify=verify)
    dm.register_domain(adapter)
    adapter.metadata["fields"].clear()
    assert dm.get_domain("latency_example").metadata["fields"]
    assert dm.verify_audit(dm.audit_domain("latency_example", sc.DEMO_CSV))
    for invalid in (None, replace(original, id="bad-id"), replace(original, schema=""),
                    replace(original, id="fresh", formats=()), replace(original, id="fresh", formats=([],)),
                    replace(original, id="fresh", load=None), original, replace(original, id="fresh"),
                    replace(original, id="fresh", schema="fresh", metadata={}),
                    replace(original, id="fresh", schema="fresh", metadata={**original.metadata, "example_format":"bad"}),
                    replace(original, id="fresh", schema="fresh", metadata={**original.metadata, "example": lambda: None})):
        with pytest.raises(ValueError):
            dm.register_domain(invalid)


def test_shared_cli_all_domains_and_custom_policy(tmp_path, capsys):
    assert main(["domains"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 3
    for domain in ("text", "segmentation", "scores"):
        path = tmp_path/(domain+".txt")
        assert main(["template", str(path), "--domain", domain]) == 0
        output = tmp_path/domain
        assert main(["demo", "--domain", domain, "--output", str(output)]) == 0
        assert main(["run", str(path), "--domain", domain, "--output", str(output), "--require-robust"]) == 1
        assert main(["verify", str(output/"report.json")]) == 0
    policy = tmp_path/"policy.json"
    policy.write_text('{"aggregations":["median"]}', encoding="utf-8")
    assert main(["run", str(path), "--domain", "scores", "--policy", str(policy), "--output", str(output), "--require-robust"]) == 0
    assert main(["scores", str(path), "--aggregations", "mean", "--output", str(output), "--require-robust"]) == 1
    assert main(["scores", str(path), "--aggregations", "median", "--output", str(output), "--require-robust"]) == 0
