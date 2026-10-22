# SPDX-License-Identifier: MIT
"""C′ 真实演示：对两个真实模型在 GSM8K 上的输出，输出一条排名主张的稳健带。
判据：S-C2（默认成立的主张在 ≥1 合法配置下翻转）；S-C3（存在 UNIDENTIFIABLE 判决）。
用法：python demo_real.py --dir data --better Qwen2.5-1.5B-Instruct --worse Qwen2.5-0.5B-Instruct
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
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import robustband as rb  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# 冻结默认（原装置选择）。2026-10-01 主跑发现它对 CoT 输出**退化**：strict_exact 把整段 CoT 当答案，
# ⟹ 与 gold 恒不等 ⟹ 两模型分数恒 0（0 vs 0），该"默认主张"其实是**空的**。
DEFAULT = "strict_exact|exact_match|micro"
# 从业者默认（GSM8K 学界事实标准：抽末行末数 + 数值容差 + micro），作**非退化**对照默认。
PRACTITIONER = "last_line_num|numeric_tol|micro"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data")
    ap.add_argument("--better", default="Qwen2.5-1.5B-Instruct")
    ap.add_argument("--worse", default="Qwen2.5-0.5B-Instruct")
    ap.add_argument("--default", default=DEFAULT,
                    help="默认协议 parse|metric|agg（默认 " + DEFAULT + "）")
    args = ap.parse_args()
    default_cfg = args.default

    root = args.dir if os.path.isabs(args.dir) else os.path.join(HERE, args.dir)
    preds = rb.JSONLAdapter(root, models=[args.better, args.worse]).load()
    missing = [m for m in (args.better, args.worse) if m not in preds]
    if missing:
        print(f"[ERR] 缺模型输出文件：{missing}（预期 {root}/<model>.jsonl）")
        return 1
    n = min(len(preds[args.better]["items"]), len(preds[args.worse]["items"]))
    # 对齐（2026-10-01）：两模型均以同一 --offset / items.json 顺序生成 ⟹ 行 i 对应同一 item；
    # 生成可能因内存崩溃导致长度不等 ⟹ 截断到公共前缀，保证逐 item 配对（否则 micro 分母不同、非可比）。
    for m in (args.better, args.worse):
        preds[m]["items"] = preds[m]["items"][:n]
    print(f"[data] 对齐后 {n} items/模型；better={args.better} worse={args.worse}")

    claim = rb.RankClaim(args.better, args.worse)
    family = rb.build_family()
    band = rb.evaluate(preds, family, claim)
    cert = rb.certificate.emit(preds, family, claim, band)

    # 默认协议下的读数
    tbl = rb.score_table(preds, rb.Perturbation(*default_cfg.split("|")))
    print(f"\n默认协议 {default_cfg}:")
    print(f"  {args.better} = {tbl[args.better]:.4f}")
    print(f"  {args.worse}  = {tbl[args.worse]:.4f}")
    print(f"  margin = {tbl[args.better]-tbl[args.worse]:+.4f}  (默认主张 {'成立' if claim.holds(tbl) else '不成立'})")

    # 对照·从业者默认（GSM8K 事实标准，非退化）
    tbl_prac = rb.score_table(preds, rb.Perturbation(*PRACTITIONER.split("|")))
    print(f"\n对照·从业者默认 {PRACTITIONER}:")
    print(f"  {args.better} = {tbl_prac[args.better]:.4f}")
    print(f"  {args.worse}  = {tbl_prac[args.worse]:.4f}")
    print(f"  margin = {tbl_prac[args.better]-tbl_prac[args.worse]:+.4f}  "
          f"(主张 {'成立' if claim.holds(tbl_prac) else '不成立'})")

    print(f"\n稳健带（{band.n_configs} 配置）:")
    print(f"  稳健比例 = {band.stability_fraction:.4f}  破坏集 = {len(band.break_set)}")
    print(f"  δ 带 = ({band.delta[0]:+.4f}, {band.delta[1]:+.4f})   判决 = {band.verdict}")

    # 破坏集示例（含 margin 的极值配置）
    if band.break_set:
        ex = sorted(band.break_set, key=lambda k: band.margins[k])[:6]
        print("  翻转示例（配置 | margin）:")
        for k in ex:
            print(f"    {k} | {band.margins[k]:+.4f}")

    # 判据（对齐预注册 §四 S-C2 冻结语义："默认协议下成立" ∧ "≥1 合法成员下翻转"）
    # ⚠ 原实现 s_c2 仅测 len(break_set)>0，**从未检查"默认成立"**；且冻结默认对 CoT 退化（0=0，
    #   RankClaim.holds 为严格 > ⟹ 冻结默认自身即在 break_set 内）。此偏差于 §九 跑后留痕，此处并列口径。
    s_c2_weak = len(band.break_set) > 0                 # 原实现（弱：仅"存在翻转"）
    dh_frozen = claim.holds(tbl)                        # 冻结默认是否成立
    dh_pract = claim.holds(tbl_prac)                    # 从业者默认是否成立
    s_c2_strict_frozen = dh_frozen and s_c2_weak        # 严格口径（冻结默认）
    s_c2 = dh_pract and s_c2_weak                       # 严格口径（从业者默认）；S_C2 键取此
    s_c3 = band.verdict == "UNIDENTIFIABLE"
    s_c4 = cert is not None
    print(f"\n判据（预注册 §四 严格口径）:")
    print(f"  默认成立? 冻结={dh_frozen}  从业者={dh_pract}")
    print(f"  S-C2: 严格(冻结默认)={s_c2_strict_frozen}  严格(从业者默认)={s_c2}  弱口径(原实现)={s_c2_weak}")
    print(f"  S-C3(不可识别)={s_c3}  S-C4(证书可交付)={s_c4}")
    if cert:
        print(f"  证书类型 = {cert['type']}")
        if cert["type"] == "minimal_counterexample":
            print(f"  最小反例 = {cert['config']}  margin={cert['margin']:+.4f}")
        else:
            print(f"  {cert['statement']}")

    out = {"better": args.better, "worse": args.worse, "n": n,
           "default": default_cfg, "default_table": tbl,
           "practitioner": PRACTITIONER, "practitioner_table": tbl_prac,
           "band": band.to_dict(),
           "S_C2": s_c2, "S_C2_weak": s_c2_weak,
           "S_C2_strict_frozen": s_c2_strict_frozen, "S_C2_strict_practitioner": s_c2,
           "default_holds_frozen": dh_frozen, "default_holds_practitioner": dh_pract,
           "S_C3": s_c3, "S_C4": s_c4,
           "certificate": cert}
    rp = os.path.join(HERE, "..", "results", "demo_real_result.json")
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    json.dump(out, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n[done] -> {os.path.abspath(rp)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
