# SPDX-License-Identifier: MIT
"""Shared report layer: escaping, tones, figure geometry and self-containment."""
from copy import deepcopy

import pytest

from robustband import decision as d
from robustband.report import render_html
from robustband.report_style import (_float, badge, band_svg, page, safe, styles, table)
from robustband.workflow import DEMO_CSV, DEFAULT_FAMILY


def test_safe_escapes_text_and_attribute_contexts():
    assert safe("<script>") == "&lt;script&gt;"
    assert safe('" onload="x') == "&quot; onload=&quot;x"


def test_badge_tones_and_invalid_tone():
    assert "badge ok" in badge("稳健", "ok") and "稳健" in badge("稳健", "ok")
    assert "badge warn" in badge("x", "warn") and "badge bad" in badge("x", "bad")
    assert badge("x") == "<span class='badge'>x</span>"
    with pytest.raises(ValueError, match="Unknown badge tone"):
        badge("x", "critical")


def test_table_caption_scroll_and_escaping():
    plain = table(["a"], [["<b>"]], caption="note", scroll=False)
    assert plain.startswith("<table>") and "<caption" in plain and "&lt;b&gt;" in plain
    assert "scroll" in table(["a"], [["b"]])


def test_page_is_self_contained_and_declares_language():
    html = page("t <x>", "<p>body</p>", lang="zh")
    assert html.startswith("<!doctype html>") and "lang='zh'" in html
    assert "<style>" in html and "body" in html
    assert "t &lt;x&gt;" in html and "<script" not in html
    assert "@media print" in styles()


def test_band_svg_marks_both_witnesses_and_the_zero_line():
    figure = band_svg(-0.5, 1.0, "-1/2", "1", title="规则范围")
    assert "role='img'" in figure and "<desc" in figure
    assert "-1/2" in figure and ">1<" in figure
    assert "<circle" in figure and "<path" in figure          # shape-coded endpoints
    assert "stroke-dasharray" in figure                        # zero line, always drawn
    assert "规则范围" in figure


def test_band_svg_handles_one_sided_and_degenerate_ranges():
    from robustband.report_style import SOFT, WARN_SOFT
    positive = band_svg(0.5, 2.0, "1/2", "2")
    assert "stroke-dasharray" in positive                      # zero stays visible outside the range
    assert WARN_SOFT not in positive and SOFT in positive       # no negative segment
    negative = band_svg(-2.0, -0.5, "-2", "-1/2")
    assert SOFT not in negative and WARN_SOFT in negative
    degenerate = band_svg(0, 0, "0", "0")                       # all-zero band stays visible
    assert "viewBox" in degenerate and "<circle" in degenerate
    assert "width='2' height='26.0'" in degenerate
    assert degenerate.count(">3 pp</text>") == 0
    single = band_svg(3, 3, "3 pp", "3 pp")
    assert single.count("3 pp</text>") == 1                      # one centred label, not two
    assert _float("13/200") == 0.065


def test_text_decision_report_uses_the_shared_figure():
    plan = deepcopy(d.EXAMPLE_PLAN)
    plan["domain"] = "text"
    plan["targets"] = plan["targets"][:1]
    target = plan["targets"][0]
    for key in ("metric", "unit", "direction"):
        target.pop(key)
    target["family"] = deepcopy(DEFAULT_FAMILY)
    report = d.analyze_decision(DEMO_CSV, plan, edition="professional")
    html = render_html(report)                                 # text audits carry no plot_band
    assert "Adoption check" in html and "<svg" in html
    assert "objective tradeoff" in html or "Review rule sensitivity" in html
