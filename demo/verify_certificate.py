# SPDX-License-Identifier: MIT
"""独立复算验证脚本（E 负模块配套）。
读 ../results/emodule_bundle.json，**不信任**其中的读数，用 robustband 引擎重算：
  V1 最小反例 config 确实使主张翻转（holds=False 且 margin<0 与证书一致）
  V2 不可行性证书的 δ 带确含 0，且 [+] / [−] 见证确为全族 margin 的极值
  V3 稳健比例与 break_set 大小自洽（stab == 1 - |break|/n_configs）
任一不符 ⟹ 退出码 2（证书不可复现）。

用法：python verify_certificate.py
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
BUNDLE = os.path.join(HERE, "..", "results", "emodule_bundle.json")


def main():
    b = json.load(open(BUNDLE, encoding="utf-8"))
    claim_d = b["claim"]
    better, worse = claim_d["better"], claim_d["worse"]
    # 数据目录从 bundle 读取（bundle 自记 data_dir），保证与生成 bundle 时一致
    data_dir = b.get("data_dir", "data")
    root = data_dir if os.path.isabs(data_dir) else os.path.join(HERE, data_dir)
    preds = rb.JSONLAdapter(root, models=[better, worse]).load()
    n = min(len(preds[better]["items"]), len(preds[worse]["items"]))
    for mm in (better, worse):  # 对齐公共前缀（与 demo_real/emodule_bundle 一致）
        preds[mm]["items"] = preds[mm]["items"][:n]
    claim = rb.RankClaim(better, worse)
    family = rb.build_family()
    band = rb.evaluate(preds, family, claim)

    fails = []

    # V1 最小反例
    mce = b.get("minimal_counterexample")
    if mce is None:
        print("V1 [skip] bundle 无最小反例（仅不可行性证书）")
    else:
        h = rb.Perturbation(*mce["config"].split("|"))
        t = rb.score_table(preds, h)
        holds = claim.holds(t)
        m = claim.margin(t)
        ok = (not holds) and abs(m - mce["margin"]) < 1e-12
        print(f"V1 最小反例 {mce['config']}: holds={holds} margin={m:+.6f} "
              f"(证书 {mce['margin']:+.6f}) -> {'PASS' if ok else 'FAIL'}")
        if not ok:
            fails.append("V1")

    # V1b 最强反例（真·反转：worse 严格反超 better）
    sce = b.get("strongest_counterexample")
    if sce is None:
        print("V1b [skip] bundle 无最强反例（无 margin<0 的合法配置）")
    else:
        h = rb.Perturbation(*sce["config"].split("|"))
        t = rb.score_table(preds, h)
        m = claim.margin(t)
        ok = (not claim.holds(t)) and (m < 0) and abs(m - sce["margin"]) < 1e-12
        print(f"V1b 最强反例 {sce['config']}: margin={m:+.6f} ({better}={t[better]:.4f} < {worse}={t[worse]:.4f}) "
              f"-> {'PASS' if ok else 'FAIL'}")
        if not ok:
            fails.append("V1b")

    # V2 不可行性证书
    imp = b.get("impossibility_certificate")
    if imp is None:
        print("V2 [skip] bundle 无不可行性证书")
    else:
        lo, hi = band.delta
        contains0 = lo <= 0 <= hi
        wp = imp["witness_positive"]["config"]
        wn = imp["witness_negative"]["config"]
        argmax = max(band.margins, key=band.margins.get)
        argmin = min(band.margins, key=band.margins.get)
        ok = contains0 and (wp == argmax) and (wn == argmin)
        print(f"V2 不可识别: δ=({lo:+.6f},{hi:+.6f}) 含0={contains0} "
              f"见证[+]={wp}{'✔' if wp==argmax else '✘'} 见证[−]={wn}{'✔' if wn==argmin else '✘'} "
              f"-> {'PASS' if ok else 'FAIL'}")
        if not ok:
            fails.append("V2")

    # V3 自洽
    stab_ok = abs(band.stability_fraction - (1 - len(band.break_set) / band.n_configs)) < 1e-12
    n_ok = band.n_configs == len(band.margins)
    print(f"V3 自洽: stab={band.stability_fraction:.4f} break={len(band.break_set)}/{band.n_configs} "
          f"({len(band.margins)} margins) -> {'PASS' if (stab_ok and n_ok) else 'FAIL'}")
    if not (stab_ok and n_ok):
        fails.append("V3")

    if fails:
        print(f"\n[VERIFY FAIL] {fails}")
        return 2
    print("\n[VERIFY PASS] 证书可独立复现")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
