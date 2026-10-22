# SPDX-License-Identifier: MIT
"""真实数据的稳健带细读（跑后分析，不改任何冻结判据）。
读 data/ 下两模型 jsonl，输出：关键协议分数表、80 配置 margin 排序、真正的 ± 反转对。
用法：python analyze_real.py
"""

# 控制台健壮性：Windows 传统控制台默认 GBK，无法编码中文/−/✔ 等字形会直接崩溃。
# 强制 UTF-8 输出（现代终端正确渲染；无法编码的字符以替代符输出，绝不崩溃）。
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import robustband as rb

HERE = os.path.dirname(os.path.abspath(__file__))
A = "Qwen2.5-1.5B-Instruct"   # better(名义)
B = "Qwen2.5-0.5B-Instruct"   # worse(名义)
DEFAULT = rb.Perturbation("strict_exact", "exact_match", "micro")

preds = rb.JSONLAdapter(os.path.join(HERE, "data"), models=[A, B]).load()
n = min(len(preds[A]["items"]), len(preds[B]["items"]))
print(f"items/models = {n} ;  A={A}  B={B}\n")

NAMED = [
    ("冻结默认", "strict_exact", "exact_match", "micro"),
    ("从业者标准(last-line-num)", "last_line_num", "numeric_tol", "micro"),
    ("末数", "last_num", "exact_match", "micro"),
    ("boxed", "boxed", "exact_match", "micro"),
    ("首数", "first_num", "exact_match", "micro"),
    ("首数+contains+class", "first_num", "contains", "macro_class"),
    ("strict_exact+contains+median", "strict_exact", "contains", "median"),
]
print("== 关键协议分数表 ==")
print(f"{'协议':32s} {A[:18]:>18s} {B[:18]:>18s} {'margin':>10s}")
for name, p, m, g in NAMED:
    tbl = rb.score_table(preds, rb.Perturbation(p, m, g))
    d = tbl[A] - tbl[B]
    print(f"{name:32s} {tbl[A]:18.4f} {tbl[B]:18.4f} {d:+10.4f}")

fam = rb.build_family()
band = rb.evaluate(preds, fam, rb.RankClaim(A, B))
marg = band.margins
print(f"\n== 全 {len(fam)} 配置 margin 统计 ==")
vals = sorted(marg.values())
pos = [c for c, v in marg.items() if v > 0]
neg = [c for c, v in marg.items() if v < 0]
zero = [c for c, v in marg.items() if v == 0]
print(f"  >0（{A}优）: {len(pos)}    <0（{B}优）: {len(neg)}    ==0: {len(zero)}")
print(f"  min = {vals[0]:+.6f}   max = {vals[-1]:+.6f}   span 含0 = {vals[0] <= 0 <= vals[-1]}")

print("\n== 最负（B 胜）的 8 个配置 ==")
for c in sorted(marg, key=lambda k: marg[k])[:8]:
    print(f"  {marg[c]:+.6f}  {c}")

print("\n== 去退化后：严格反号的合法协议对（p>0 且 q<0，均非 strict_exact 退化行）==")
def nondeg(c):
    return not c.startswith("strict_exact")
neg_nd = [c for c in sorted(neg) if nondeg(c)]
pos_nd = [c for c in sorted(pos, key=lambda k: -marg[k]) if nondeg(c)]
if neg_nd and pos_nd:
    print(f"  正: {pos_nd[0]}  margin={marg[pos_nd[0]]:+.6f}")
    print(f"  负: {neg_nd[0]}  margin={marg[neg_nd[0]]:+.6f}")
    print(f"  ⟹ 两合法协议给出相反 winner（幅度比 {abs(marg[pos_nd[0]]/marg[neg_nd[0]]):.0f}×）")

out = {
    "n": n, "A": A, "B": B,
    "scores": {f"{p}|{m}|{g}": rb.score_table(preds, rb.Perturbation(p, m, g)) for p, m, g in
               [(p, m, g) for _, p, m, g in NAMED]},
    "n_pos": len(pos), "n_neg": len(neg), "n_zero": len(zero),
    "min": vals[0], "max": vals[-1],
    "neg_nondeg": neg_nd, "pos_nondeg_top": pos_nd[0] if pos_nd else None,
}

# ---- 非退化 ℋ：两模型得分均 > 0 的协议子集（排除「判分恒 0」的退化操作点）----
tabs = {c: rb.score_table(preds, rb.Perturbation(*c.split("|"))) for c in marg}
nd = [c for c in marg if tabs[c][A] > 0 and tabs[c][B] > 0]
nd_m = {c: marg[c] for c in nd}
nd_neg = [c for c in nd if nd_m[c] < 0]
nd_pos = [c for c in nd if nd_m[c] > 0]
print(f"\n== 非退化 ℋ（两模型分均>0）：{len(nd)}/{len(marg)} 配置 ==")
if nd:
    lo, hi = min(nd_m.values()), max(nd_m.values())
    print(f"  δ_nd = ({lo:+.6f}, {hi:+.6f})   含0 = {lo <= 0 <= hi}   (<0: {len(nd_neg)}  >0: {len(nd_pos)})")
    if nd_neg:
        print(f"  最负(非退化) = {min(nd_neg, key=lambda c: nd_m[c])}  {min(nd_m.values()):+.6f}")

# 逐 item 判定（真实 API：PARSE[h.parse] 解析 → METRIC[h.metric] 判分）
def item_corrects(blob, h):
    p, m = rb.PARSE[h.parse], rb.METRIC[h.metric]
    return [m(p(raw), gold, meta) for raw, gold, meta in blob["items"]]

def per_item(h, thresh=0.5):
    ca, cb = item_corrects(preds[A], h), item_corrects(preds[B], h)
    return sum(1 for i in range(n) if (ca[i] >= thresh) != (cb[i] >= thresh))

def flips_for(h):
    ca, cb = item_corrects(preds[A], h), item_corrects(preds[B], h)
    return [i for i in range(n) if (ca[i] >= 0.5) != (cb[i] >= 0.5)]

print(f"\n== 默认协议逐 item 分歧（两者判分同 0 ⟹ 应为 0）: {per_item(DEFAULT)} ==")
if nd_neg:
    worst = min(nd_neg, key=lambda c: nd_m[c])
    hw = rb.Perturbation(*worst.split("|"))
    fl = flips_for(hw)
    print(f"== 最负见证 {worst}: 翻转 item = {len(fl)}  → A/B 判分 {[ (round(item_corrects(preds[A],hw)[i],3), round(item_corrects(preds[B],hw)[i],3)) for i in fl[:5] ]} ==")

out["nd_n"] = len(nd)
out["nd_delta"] = [min(nd_m.values()), max(nd_m.values())] if nd else None
out["nd_neg"] = nd_neg
out["per_item_default"] = per_item(DEFAULT)
out["flip_items_worst"] = len(fl) if nd_neg else None
json.dump(out, open(os.path.join(HERE, "..", "results", "analyze_real.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n[done] results/analyze_real.json")
