# SPDX-License-Identifier: MIT
"""A3 · E 负模块：一条主张的「最小可复现反例」自足包（config + 数字 + 证书）。

自足：只依赖 data/ 下两个 .jsonl + robustband。不重生成任何模型输出。
用法：
  python e_reproduce.py --dir data --better Qwen0.5B_cot --worse Qwen0.5B_plain \
      --default "last_num|exact_match|micro"

输出：
  (1) 默认协议下的边际（应>0，即主张成立）；
  (2) 扫描 ℋ 全部合法配置，取**边际最小者**作最小反例 h*；
  (3) 若 h* 的边际与默认**反号** ⟹ 出具 impossibility_certificate（含 config/命令/证书）。
  证书落 ../results/e_counterexample.json。
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data")
    ap.add_argument("--better", default="Qwen0.5B_cot")
    ap.add_argument("--worse", default="Qwen0.5B_plain")
    ap.add_argument("--default", default="last_num|exact_match|micro")
    args = ap.parse_args()

    root = args.dir if os.path.isabs(args.dir) else os.path.join(HERE, args.dir)
    preds = rb.JSONLAdapter(root, models=[args.better, args.worse]).load()
    miss = [m for m in (args.better, args.worse) if m not in preds]
    if miss:
        print(f"[ERR] 缺输出：{miss}")
        return 1

    claim = rb.RankClaim(args.better, args.worse)
    family = rb.build_family()
    band = rb.evaluate(preds, family, claim)

    def margin(cfg):
        tbl = rb.score_table(preds, rb.Perturbation(*cfg.split("|")))
        return tbl[args.better] - tbl[args.worse]

    m_def = margin(args.default)
    holds = m_def > 0
    print(f"[默认] {args.default}  margin = {m_def:+.4f}  (主张 {'成立' if holds else '不成立'})")
    print(f"[带]   δ = ({band.delta[0]:+.4f}, {band.delta[1]:+.4f})  判决 = {band.verdict}  "
          f"stable = {band.stability_fraction:.4f}  break = {len(band.break_set)}/{band.n_configs}")

    # 最小反例 = 边际最小（最负）的合法配置，且与默认反号
    h_star = min(band.margins, key=lambda k: band.margins[k])
    m_star = band.margins[h_star]
    flips = holds and (m_star < 0)
    print(f"[反例] h* = {h_star}  margin = {m_star:+.4f}  ⟹ {'反号 (翻转)' if flips else '未反号'}")

    cert = {
        "type": "minimal_counterexample" if flips else "no_counterexample",
        "claim": {"kind": "rank", "better": args.better, "worse": args.worse},
        "default": {"config": args.default, "margin": m_def, "holds": holds},
        "counterexample": {"config": h_star, "margin": m_star, "holds": (m_star > 0)},
        "band": {"delta": band.delta, "verdict": band.verdict,
                 "stability_fraction": band.stability_fraction,
                 "n_break": len(band.break_set), "n_configs": band.n_configs},
        "reproduce_cmd": (
            f"python e_reproduce.py --dir {os.path.relpath(root, HERE)} "
            f"--better {args.better} --worse {args.worse} --default \"{args.default}\""
        ),
        "witness_negative": {"config": h_star, "margin": m_star},
    }
    if flips:
        cert["statement"] = (
            f"主张「{args.better} 优于 {args.worse}」在默认协议 {args.default} 下成立（m={m_def:+.4f}），"
            f"但在同为合法的配置 {h_star} 下反号（m={m_star:+.4f}）⟹ 该主张方向不可由协议确定。"
        )

    rp = os.path.join(HERE, "..", "results", "e_counterexample.json")
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    json.dump(cert, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n[证书] {cert['type']}")
    if flips:
        print(f"  {cert['statement']}")
    print(f"[done] -> {os.path.abspath(rp)}")
    return 0 if flips else 2


if __name__ == "__main__":
    raise SystemExit(main())
