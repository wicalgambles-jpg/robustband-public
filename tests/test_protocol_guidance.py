# SPDX-License-Identifier: MIT
"""Reproduce user-reported rule consequences without changing frozen scorers."""
from copy import deepcopy

from robustband import metrics, parsers, workflow
from robustband.domains import domain_options
from robustband.protocol_guidance import text_rule_cautions
from robustband.report import render_html


def test_selected_rules_explain_the_reported_semantics_and_metadata_is_isolated():
    assert metrics.m_contains("142", "42") == 1
    assert parsers.p_first_num("1,234") == "1"
    assert parsers.p_last_num("1,234") == "234"
    family = {"parses": ["first_num", "boxed"], "metrics": ["contains"], "aggs": ["median"]}
    notes = text_rule_cautions(family)
    assert {n["id"] for n in notes} == {"substring", "binary-median", "number-format"}
    notes[0]["message"]["en"] = "changed"
    assert "142" in text_rule_cautions(family)[0]["message"]["en"]
    assert text_rule_cautions({"parses": ["strict_exact"], "metrics": ["exact_match"], "aggs": ["micro"]}) == []
    assert text_rule_cautions({"aggregations": ["median"]}) == []  # Other domains have their own targets.
    options = domain_options("professional")[0]
    contains = next(o for c in options["controls"] for o in c["options"] if o["value"] == "contains")
    assert contains["cautions"][0]["id"] == "substring"


def test_median_tie_is_distinguished_from_a_strict_reversal_and_replays():
    rows = [{"sample_id": str(i), "prompt": "Answer", "gold": "42",
             "output_a": "42" if i < 9 else "0", "output_b": "42" if i < 6 else "0"}
            for i in range(10)]
    family = {"parses": ["strict_exact"], "metrics": ["exact_match"], "aggs": ["micro", "median"]}
    report = workflow.analyze(rows, family)
    assert [(c["score_a"], c["score_b"]) for c in report["configurations"]] == [("9/10", "3/5"), ("1", "1")]
    assert report["result"]["exact_band"] == ["0", "3/10"]
    assert report["result"]["verdict"] == "UNIDENTIFIABLE"
    assert report["result"]["strict_sign_flip"] is False and report["result"]["reverse_count"] == 0
    assert workflow.verify_report(report)
    before = deepcopy(report)
    html = render_html(report)
    assert "领先与打平并存" in html and "60%" in html and report == before
    family["aggs"] = ["micro"]
    mean = workflow.analyze(rows, family)
    assert mean["result"]["verdict"] == "ROBUST" and "60%" not in render_html(mean)
    tied = workflow.analyze([dict(rows[0], output_b="42")], family)
    assert "所选规则下全部打平" in render_html(tied)
