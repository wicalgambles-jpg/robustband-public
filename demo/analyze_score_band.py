# SPDX-License-Identifier: MIT
"""C′ 真实数据的「阈值主张」稳健带（跑后分析，不改任何冻结判据）。

把排名主张（RankClaim: A>B）换成**分数-阈值**主张（ScoreClaim: M > t），展示：
同一模型、同一 benchmark 上，「分数是否超过 t」的答案**完全由评分协议决定**——
分数是**区间**而非点，任何落在区间内的阈值主张都**不可识别**。这是决策相关的
强异常（幅度 = 区间宽度），且**零模型开销**（A 档仅计分）。

用法：python analyze_score_band.py
"""

# 控制台健壮性：Windows 传统控制台默认 GBK，无法编码中文/−/✔ 等字形会直接崩溃。
# 强制 UTF-8 输出（现代终端正确渲染；无法编码的字符以替代符输出，绝不崩溃）。
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import robustband as rb  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = ["Qwen2.5-1.5B-Instruct", "Qwen2.5-0.5B-Instruct"]
PRACT = "last_line_num|numeric_tol|micro"       # GSM8K 学界事实标准（非退化）
FROZEN = "strict_exact|exact_match|micro"       # 原冻结默认（对 CoT 退化）
THRESHOLDS = [0.20, 0.30, 0.40, 0.50]

preds = rb.JSONLAdapter(os.path.join(HERE, "data"), models=MODELS).load()
fam = rb.build_family()

print(f"配置数 = {len(fam)}；模型 = {MODELS}\n")

out = {"models": {}, "thresholds": THRESHOLDS, "practitioner": PRACT, "frozen": FROZEN}
for M in MODELS:
    # 单模型分数在 80 配置上的区间
    scores = {str(h): rb.score_table(preds, h)[M] for h in fam}
    vals = sorted(scores.values())
    lo, hi = vals[0], vals[-1]
    med = vals[len(vals) // 2]
    s_frozen = rb.score_table(preds, rb.Perturbation(*FROZEN.split("|")))[M]
    s_pract = rb.score_table(preds, rb.Perturbation(*PRACT.split("|")))[M]
    print(f"== {M} ==")
    print(f"  分数区间 across {len(fam)} 配置: [{lo:.4f}, {hi:.4f}]  (中位 {med:.4f})")
    print(f"    最小配置 = {min(scores, key=scores.get)}  ({lo:.4f})")
    print(f"    最大配置 = {max(scores, key=scores.get)}  ({hi:.4f})")
    print(f"  冻结默认  {FROZEN}: {s_frozen:.4f}")
    print(f"  从业者默认 {PRACT}: {s_pract:.4f}")
    out["models"][M] = {
        "score_range": [lo, hi], "score_median": med,
        "min_cfg": min(scores, key=scores.get), "max_cfg": max(scores, key=scores.get),
        "score_frozen": s_frozen, "score_practitioner": s_pract,
        "scores": scores, "thresholds": {},
    }

    print(f"  阈值主张『{M} > t』的稳健带：")
    for t in THRESHOLDS:
        claim = rb.ScoreClaim(M, t)
        band = rb.evaluate(preds, fam, claim)
        dh_p = claim.holds(rb.score_table(preds, rb.Perturbation(*PRACT.split("|"))))
        print(f"    t={t:.2f}: δ=({band.delta[0]:+.4f}, {band.delta[1]:+.4f})  "
              f"verdict={band.verdict:14s}  翻转={len(band.break_set):2d}  "
              f"从业者默认成立={dh_p}")
        out["models"][M]["thresholds"][f"{t:.2f}"] = {
            "delta": list(band.delta), "verdict": band.verdict,
            "n_break": len(band.break_set), "holds_practitioner": dh_p,
        }

    # 强异常见证（取 t 落在分数区间中段的那个阈值）
    t_mid = min(THRESHOLDS, key=lambda t: abs(t - med))
    claim = rb.ScoreClaim(M, t_mid)
    band = rb.evaluate(preds, fam, claim)
    cert = rb.certificate.emit(preds, fam, claim, band)
    print(f"  强异常见证  t={t_mid:.2f}: 正 {cert.get('witness_positive')}  "
          f"负 {cert.get('witness_negative')}")
    out["models"][M]["strong_witness"] = {"t": t_mid, "cert": cert}
    print()

json.dump(out, open(os.path.join(HERE, "..", "results", "analyze_score_band.json"), "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print("[done] results/analyze_score_band.json")
