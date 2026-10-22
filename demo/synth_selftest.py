# SPDX-License-Identifier: MIT
"""S-C1 引擎正确性自检：robustband vs 独立蛮力 ref_impl。
合成数据（确定性），覆盖 3 类主张（rank / score），比较 stability_fraction / break_set / delta / 逐配置 margin。
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
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import robustband as rb  # noqa: E402
import ref_impl as ref  # noqa: E402


def synth_preds(n_items=120, seed=0):
    """构造两模型 + 一个 gold；模型 A 稍强。
    输出故意混杂：有的带 #### 尾数、有的带 \\boxed、有的是整句、有的是小数。
    """
    rng = random.Random(seed)
    itemsA, itemsB = [], []
    for i in range(n_items):
        if i % 4 == 0:
            gold = str(rng.randint(1, 200))
            rawA = f"... reasoning ... #### {gold}"  # 正确但需抽取
            rawB = f"I think the answer is {gold}."  # 正确但需抽取
        elif i % 4 == 1:
            gold = f"{rng.randint(10, 99)}.{rng.randint(0,9)}"
            rawA = f"\\boxed{{{gold}}}"
            rawB = f"the value is {gold} approximately"
        elif i % 4 == 2:
            gold = str(rng.randint(1, 50))
            rawA = f"final: {gold}"
            rawB = f"not sure, maybe {rng.randint(1,50)}"  # 可能错
        else:
            gold = f"{rng.randint(1, 20)}"
            rawA = f"answer {gold}"  # 正确
            rawB = f"{rng.randint(1,20)}"  # 裸数，可能错
        metaA = {"class": f"c{i%5}", "len_bucket": i % 3}
        metaB = {"class": f"c{i%5}", "len_bucket": i % 3}
        itemsA.append((rawA, gold, metaA))
        itemsB.append((rawB, gold, metaB))
    return {"A": {"items": itemsA}, "B": {"items": itemsB}}


def run_one(preds, claim, claim_kind, claim_args, tag):
    family = rb.build_family()
    band = rb.evaluate(preds, family, claim)
    r_stab, r_break, r_lo, r_hi, r_margins = ref.ref_evaluate(
        preds, list(rb.PARSE), list(rb.METRIC), list(rb.AGG), claim_kind, claim_args
    )
    ok = True
    msgs = []
    if abs(band.stability_fraction - r_stab) > 1e-12:
        ok = False
        msgs.append(f"stability {band.stability_fraction} != {r_stab}")
    if sorted(band.break_set) != r_break:
        ok = False
        msgs.append(f"break_set mismatch ({len(band.break_set)} vs {len(r_break)})")
    if abs(band.delta[0] - r_lo) > 1e-12 or abs(band.delta[1] - r_hi) > 1e-12:
        ok = False
        msgs.append(f"delta {band.delta} != ({r_lo},{r_hi})")
    # 逐配置 margin
    maxd = 0.0
    for k, v in band.margins.items():
        maxd = max(maxd, abs(v - r_margins[k]))
    if maxd > 1e-12:
        ok = False
        msgs.append(f"per-config margin maxdiff {maxd:.3e}")
    print(f"[{tag}] claim={claim.name} n_configs={band.n_configs} "
          f"stab={band.stability_fraction:.4f} breaks={len(band.break_set)} "
          f"delta=({band.delta[0]:.4f},{band.delta[1]:.4f}) verdict={band.verdict} "
          f"maxdiff={maxd:.2e} -> {'PASS' if ok else 'FAIL: ' + '; '.join(msgs)}")
    return ok


def main():
    preds = synth_preds()
    results = []
    # 1) rank 主张 A>B
    results.append(run_one(preds, rb.RankClaim("A", "B"), "rank", ("A", "B"), "C1-rank-A>B"))
    # 2) rank 主张 B>A（预期被反驳或不可识别）
    results.append(run_one(preds, rb.RankClaim("B", "A"), "rank", ("B", "A"), "C1-rank-B>A"))
    # 3) score 主张 A > 0.5
    results.append(run_one(preds, rb.ScoreClaim("A", 0.5), "score", ("A", 0.5), "C1-score-A>0.5"))

    n_pass = sum(results)
    print(f"\nS-C1 汇总: {n_pass}/{len(results)} PASS")
    print("S-C1 =", "PASS" if n_pass == len(results) else "FAIL")
    # 写出结论供回写引用
    import json
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "sc1_result.json"), "w", encoding="utf-8") as f:
        json.dump({"n_pass": n_pass, "n_total": len(results),
                   "verdict": "PASS" if n_pass == len(results) else "FAIL"}, f,
                  ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
