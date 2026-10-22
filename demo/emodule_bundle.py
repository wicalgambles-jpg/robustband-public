# SPDX-License-Identifier: MIT
"""E 负模块交付（A3）：对一条主张同时输出
  (i) 不可行性证书 impossibility_certificate（δ 带含 0 ⟹ 方向不可判定）
  (ii) 最小可复现反例 minimal_counterexample（使主张翻转的 |margin| 最小配置）
外加 (iii) 决策挂钩 decision_hook（绑定 D1/D2/D3）。
与 C′ 正面 δ-带**同版本**（同一 robustband 版本号写入 bundle）。

用法：
  python emodule_bundle.py --dir data --better Qwen2.5-0.5B-cot --worse Qwen2.5-0.5B-plain
产出：../results/emodule_bundle.json （含 repro 命令，供 verify_certificate.py 独立复算）
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
DEFAULT = "strict_exact|exact_match|micro"

# 决策挂钩（M4b 预注册的 D1/D2/D3，见 00_preregistration_FROZEN.md §六）
DECISION_HOOK = {
    "D1_eval_authors": "据 δ-带在论文中显式声明该跨配置排名『在 ℋ 下稳健/脆弱』",
    "D2_bench_maintainers": "据 break_set 停止对不稳健指标的调参 / 增加检测项",
    "D3_reviewers": "据不可识别证书要求作者补跑或据以拒稿",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data")
    ap.add_argument("--better", required=True)
    ap.add_argument("--worse", required=True)
    args = ap.parse_args()

    root = args.dir if os.path.isabs(args.dir) else os.path.join(HERE, args.dir)
    preds = rb.JSONLAdapter(root, models=[args.better, args.worse]).load()
    missing = [m for m in (args.better, args.worse) if m not in preds]
    if missing:
        print(f"[ERR] 缺模型输出文件：{missing}")
        return 1
    # 对齐到公共前缀（与 demo_real.py 一致；保证逐 item 配对，否则 micro 分母不同、非可比）
    n = min(len(preds[args.better]["items"]), len(preds[args.worse]["items"]))
    for m in (args.better, args.worse):
        preds[m]["items"] = preds[m]["items"][:n]

    claim = rb.RankClaim(args.better, args.worse)
    family = rb.build_family()
    band = rb.evaluate(preds, family, claim)

    imp = rb.certificate.impossibility_certificate(band)
    mce = rb.certificate.minimal_counterexample(preds, family, claim, band)
    # 最强反例：margin 最负的合法配置（worse 严格反超 better —— 真·排名反转，非退化平局）
    sce = None
    neg = {k: v for k, v in band.margins.items() if v < 0}
    if neg:
        kmin = min(neg, key=neg.get)
        h = next(x for x in family if str(x) == kmin)
        sce = {"type": "strongest_counterexample", "config": kmin, "margin": neg[kmin],
               "table_under_config": rb.score_table(preds, h),
               "repro": {"parse": h.parse, "metric": h.metric, "agg": h.agg, "claim": claim.name}}

    bundle = {
        "robustband_version": rb.__version__,
        "data_dir": args.dir,
        "claim": {"kind": claim.kind, "better": args.better, "worse": args.worse, "name": claim.name},
        "n_configs": band.n_configs,
        "band": band.to_dict(),
        "impossibility_certificate": imp,
        "minimal_counterexample": mce,
        "strongest_counterexample": sce,
        "decision_hook": DECISION_HOOK,
        "repro": {
            "bundle_cmd": f"python emodule_bundle.py --dir {args.dir} --better {args.better} --worse {args.worse}",
            "verify_cmd": "python verify_certificate.py",
            "family_axes": {
                "parse": list(rb.PARSE),
                "metric": list(rb.METRIC),
                "agg": list(rb.AGG),
            },
            "default_protocol": DEFAULT,
        },
    }

    rp = os.path.join(HERE, "..", "results", "emodule_bundle.json")
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    json.dump(bundle, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    ok_cert = imp is not None
    ok_mce = mce is not None
    print(f"[E 模块] robustband v{rb.__version__}  claim={claim.name}  n={n}  n_configs={band.n_configs}")
    print(f"  判决 = {band.verdict}   稳健比例 = {band.stability_fraction:.4f}   δ 带 = ({band.delta[0]:+.4f}, {band.delta[1]:+.4f})")
    print(f"  (i) 不可行性证书   = {'✔' if ok_cert else '—'}")
    if ok_cert:
        print(f"      见证[+] {imp['witness_positive']}")
        print(f"      见证[−] {imp['witness_negative']}")
    print(f"  (ii) 最小可复现反例 = {'✔' if ok_mce else '—'}")
    if ok_mce:
        print(f"      config = {mce['config']}   margin = {mce['margin']:+.6f}")
    print(f"  (iii) 最强反例（真·反转） = {'✔' if sce else '—'}")
    if sce:
        print(f"      config = {sce['config']}   margin = {sce['margin']:+.6f}   (worse 反超 better)")
    print(f"  A3 满足 ⟺ (i) 或 (ii) 至少其一：(i)={ok_cert}  (ii)={ok_mce}")
    print(f"[done] -> {os.path.abspath(rp)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
