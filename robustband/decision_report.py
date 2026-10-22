# SPDX-License-Identifier: MIT
"""Escaped, standalone decision reports with separate target evidence."""
import json

from .report_style import badge, band_svg, page, safe, table

LABELS = {"PASS": "条件满足 / Criteria met", "FAIL": "条件未满足 / Criteria unmet",
          "REVIEW": "需检查规则差异 / Review rule sensitivity"}
TONES = {"PASS": "ok", "FAIL": "bad", "REVIEW": "warn"}


def _band_figure(result):
    """Small rule-range figure per target, using the same geometry as the audit report."""
    labels = result.get("display_band", result.get("exact_band"))
    geometry = result.get("plot_band")
    if geometry is None:
        from .report_style import _float
        geometry = [_float(value) for value in result["exact_band"]]
    return band_svg(geometry[0], geometry[1], labels[0], labels[1],
                    title="规则范围 / Rule range", positive_means="positive margins support A")


def render_decision(report):
    """Present target tradeoffs without combining incompatible measurements."""
    result, plan = report["result"], report["plan"]
    status = result["status"]
    content = ("<div class='rh'><span class='mark'>r</span><span class='brand'>robustband</span>"
               "<span class='ver'>v" + safe(report["software_version"]) + "</span>"
               "<span class='kicker'>版本采用检查 / adoption check</span></div>")
    content += "<h1>版本采用检查 / Adoption check</h1><p class='muted'>" + safe(plan["name"]) + "</p>"
    content += ("<div class='hero'>" + badge(LABELS[status], TONES[status]) +
                "<p class='lede'>A (candidate / 候选): " + safe(report["model_a"]) +
                " · B (baseline / 基线): " + safe(report["model_b"]) + "</p>" +
                "<p class='small muted'>配对样本 / Paired samples: " + safe(result["n_items"]) +
                " · 目标 / Targets: " + safe(result["n_targets"]) + "</p></div>")
    if result["target_tradeoff"]:
        content += ("<p class='notice'>主要收益达标，但至少一项保护条件在所有所选规则下未满足。这是目标之间的取舍。 / "
                    "The primary benefit passes, while a guardrail fails under every selected rule for that target. "
                    "This is an objective tradeoff.</p>")
    summaries = []
    for target, output in zip(plan["targets"], report["targets"]):
        comparison = ">" if target["operator"] == "gt" else "≥"
        summaries.append([target["label"], target["role"], comparison + " " + target["threshold"] + " " + output["unit"],
                          "[" + ", ".join(output["display_margin_band"]) + "] " + output["unit"], LABELS[output["status"]]])
    content += table(["目标 / Target", "用途 / Role", "定向差值要求 / Requirement",
                      "规则范围 / Rule range", "结果 / Result"], summaries)
    content += "<h2>判定依据 / Decision evidence</h2><p>" + safe(plan["rationale"]) + "</p>"
    for target, output in zip(plan["targets"], report["targets"]):
        audit = output["audit"]
        content += "<h3>" + safe(target["label"]) + "</h3><p>" + safe(target["reason"]) + "</p>"
        content += _band_figure(audit["result"])
        content += ("<p class='small muted'>正值表示 A 更好；要求作用于汇总后的定向差值。 / "
                    "Positive means A is better; requirements apply to the aggregated oriented margin.</p>")
        witnesses = [audit["witnesses"]["minimum"], audit["witnesses"]["maximum"]]
        content += table(["端点 / Endpoint", "规则 / Rule", "差值 / Margin"], [
            [name, c["protocol"], c.get("display_margin", c["margin"])]
            for name, c in zip(["最低 / Minimum", "最高 / Maximum"], witnesses)])
        content += ("<p>未达标规则 / Failing rules: " +
                    safe(", ".join(output["failing_protocols"]) or "none / 无") + "</p>")
        content += "<details><summary>全部规则与适用范围 / All rules and scope</summary>"
        content += table(["规则 / Rule", "A", "B", "定向差值 / Oriented margin"], [
            [c["protocol"], c.get("display_score_a", c["score_a"]),
             c.get("display_score_b", c["score_b"]), c.get("display_margin", c["margin"])]
            for c in audit["configurations"]])
        content += ("<div class='scope'><ul>" +
                    "".join("<li>" + safe(v) + "</li>" for v in audit["warnings"] + audit["limits"]) + "</ul></div></details>")
    if report["unselected_metrics"]:
        content += ("<p>输入中未选用的指标 / Unselected metrics: " +
                    safe(", ".join(report["unselected_metrics"])) + "</p>")
    content += ("<h2>范围与复核 / Scope and replay</h2><p>规则范围不是置信区间。 / "
                "Rule ranges are not confidence intervals.</p><div class='scope'><ul>" +
                "".join("<li>" + safe(v) + "</li>" for v in report["limits"]) + "</ul></div>")
    content += ("<p class='small'>版本 / Version: " + safe(report["software_version"]) +
                " · Input SHA256: <code>" + safe(report["input_sha256"]) +
                "</code> · Plan SHA256: <code>" + safe(report["plan_sha256"]) + "</code></p>")
    content += "<p class='small'><code>python -m robustband verify report.json</code></p>"
    content += ("<details><summary>条件文件 / Decision plan</summary><pre>" +
                safe(json.dumps(plan, ensure_ascii=False, indent=2)) + "</pre></details>")
    content += ("<footer><p>robustband · MIT · 零运行时依赖 / zero runtime dependencies</p>"
                "<p>规则范围不是置信区间 / Rule ranges are not confidence intervals.</p></footer>")
    return page("robustband · Adoption check", content, lang="zh")
