# SPDX-License-Identifier: MIT
"""Self-contained HTML summaries; all user-supplied text is escaped.

The report is the artifact that leaves the app, so it uses the shared visual layer
(``report_style``) and prints the two witness protocols next to the rule range.
"""
import json
from pathlib import Path

from .report_style import _float, badge, band_svg, page, safe, table

VERDICT_TONE = {"ROBUST": ("ok", "稳健 / robust"), "REFUTED": ("bad", "被否证 / refuted"),
                "UNIDENTIFIABLE": ("warn", "结论随规则改变 / rule-sensitive")}


def _claim_text(claim):
    if "description" in claim:
        return safe(claim["description"])
    relation = " &lt; " if claim.get("direction") == "lower" else " &gt; "
    return safe(claim["model_a"]) + relation + safe(claim["model_b"])


def _protocol_rows(report):
    fields = ("protocol", "score_a", "score_b", "margin", "supports", "all_zero")
    return [[c.get("display_" + k, c[k]) for k in fields] for c in report["configurations"]]


def _sections(report):
    html = ""
    for section in report.get("sections", []):
        html += ("<h2>" + safe(section["title"]) + "</h2>" +
                 table(section["columns"], section["rows"]))
    return html


def render_html(report):
    """Readable offline report; the JSON separately keeps every replay input."""
    if report.get("schema") == "robustband.decision/v1":
        from .decision_report import render_decision
        return render_decision(report)
    if report.get("schema") == "robustband.matrix_audit/v1":
        from .matrix_report import render_matrix
        return render_matrix(report)
    result, claim = report["result"], report["claim"]
    labels = result.get("display_band", result["exact_band"])
    geometry = result.get("plot_band") or [_float(value) for value in result["exact_band"]]
    tone, tone_label = VERDICT_TONE.get(result["verdict"], ("neutral", result["verdict"]))
    minimum, maximum = report["witnesses"]["minimum"], report["witnesses"]["maximum"]

    body = ("<div class='rh'><span class='mark'>r</span><span class='brand'>robustband</span>"
            "<span class='ver'>v" + safe(report["software_version"]) + "</span>"
            "<span class='kicker'>审计报告 / audit report</span></div>")
    body += "<p class='muted small'>主张 / Claim</p><h1>" + _claim_text(claim) + "</h1>"
    body += ("<div class='hero'>" + badge(tone_label, tone) +
             "<div class='bandtext'>[" + safe(labels[0]) + ", " + safe(labels[1]) + "]</div>" +
             "<p class='lede'>" + safe(result["explanation"]) + "</p></div>")
    body += band_svg(geometry[0], geometry[1], labels[0], labels[1],
                     title="规则范围 / Rule range",
                     positive_means="positive margins support A")
    body += ("<div class='stats'>"
             "<div class='stat'><b>" + safe(result["n_items"]) + "</b><span>配对记录 / Paired records</span></div>"
             "<div class='stat'><b>" + safe(result["support_count"]) + " / " + safe(result["n_protocols"]) +
             "</b><span>支持目标的规则 / Supporting protocols</span></div>"
             "<div class='stat'><b>" + safe(result["tie_count"]) + "</b><span>差值为零的规则 / Zero margins</span></div>"
             "<div class='stat'><b>" + safe(result["reverse_count"]) + "</b><span>反向的规则 / Reversed</span></div></div>")
    body += ("<h2>两个端点 / The two endpoints</h2>" +
             table(["端点 / Endpoint", "规则 / Rule", "差值 / Margin"],
                   [["最低 / Minimum", minimum["protocol"], minimum.get("display_margin", minimum["margin"])],
                    ["最高 / Maximum", maximum["protocol"], maximum.get("display_margin", maximum["margin"])]]))
    body += ("<h2>范围与诊断 / Scope and diagnostics</h2><div class='scope'><ul>" +
             "".join("<li>" + safe(n) + "</li>" for n in report["warnings"] + report["limits"]) +
             "</ul></div>")
    body += ("<h2>逐条规则 / Declared protocol results</h2>" +
             table(["规则 / Protocol", "A", "B", "定向差值 / Oriented margin (positive favors A)",
                    "支持主张 / Supports", "全零 / Zero-score"], _protocol_rows(report)))
    body += _sections(report)
    body += ("<h2>可复算 / Reproduction</h2><p class='small'>版本 / Version: " +
             safe(report["software_version"]) + " · 输入 SHA256 / input: <code>" +
             safe(report["input_sha256"]) + "</code></p>")
    body += ("<p class='small'>配套 JSON 含输入记录、协议与源码哈希；用同一版本执行 "
             "<code>python -m robustband verify report.json</code> 可复算。复算校验一致性，"
             "不等于独立人工验证。 / The companion JSON keeps the inputs, protocols and source hashes; "
             "recomputation checks consistency, not independent human validation.</p>")
    body += ("<footer><p>robustband · MIT · 零运行时依赖 / zero runtime dependencies</p>"
             "<p>规则范围不是置信区间 / Rule ranges are not confidence intervals.</p></footer>")
    return page("robustband audit report · " + str(result["verdict"]), body, lang="zh")


def save_report(report, directory):
    """Write a matching JSON/HTML pair to an explicitly chosen local directory."""
    from .storage import write_text_atomic
    html = render_html(report)
    replay = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    directory = Path(directory)
    write_text_atomic(directory / "report.json", replay)
    write_text_atomic(directory / "report.html", html)
    return directory
