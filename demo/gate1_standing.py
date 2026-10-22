# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""C′ 主线 · Gate-1「现象站稳」包（纯 CPU，无生成，无 GPU）。

上位依据：
  - `../00_preregistration_FROZEN.md §零`（执行序：S-C1 引擎正确 → 真实基准 A 档 anomaly →
    **现象必须「站稳」（跨 seed×dataset×model×setting 复现，Gate 1）** → 之后才进 Gate-3/M4a）。
  - `../01_MVP结果报告_A2.md`（A2 MVP：24 项配对 δ 带 (−0.041667, +0.065) 含 0 ⟹ UNIDENTIFIABLE）。

目的：把 A2 的「24 项玩具」升级为**跨规模 / 跨样本 / 跨子族**三重稳健的现象，
回答三个最可能的审稿质疑：
  (Q1) 「24 项太少，full test 上会不会消失？」  -> P1 全量 n=1319 分带
  (Q2) 「只是这 24 项恰好如此？」              -> P2 逐项 bootstrap（配对重采样 B=2000）
  (Q3) 「只是这 80 条里的某条怪配置？」          -> P3 ℋ 子族敏感性（留一值 / 单轴）

── 冻结判据（M4，**跑前写死**；本文件顶部即冻结文本，运行后不得改判据）──
  G1-1（全量分带）：full n=1319 的 80 协议分数带满足  width = hi−lo ≥ 0.10  **且**  ratio = hi/lo ≥ 3.0。
  G1-2（逐项 bootstrap）：B=2000 配对重采样上  P(UNIDENTIFIABLE) ≥ 0.90  **且**  P(sign-flip, min<0∧max>0) ≥ 0.50。
  G1-3（ℋ 子族敏感性）：对全部 13 个「留一轴值」子族，**每一个**的 80→子族带**仍含 0**（UNIDENTIFIABLE 保持）。
  判决：Gate-1 站稳 ⟺ G1-1 ∧ G1-2 ∧ G1-3；否则 PARTIAL（逐条报告哪条未过）。

结论等级：现象层证据 = `C`（真实数据上的稳健带 anomaly）；不变「已占 slot」判读（Gate-3 另做）。
"""

# 控制台健壮性：Windows 传统控制台默认 GBK，无法编码中文/−/✔ 等字形会直接崩溃。
# 强制 UTF-8 输出（现代终端正确渲染；无法编码的字符以替代符输出，绝不崩溃）。
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import sys, os, json, random
from itertools import product

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import robustband as rb
from robustband.compiled import CompiledScores
from robustband.core import Perturbation, build_family, score_table, evaluate
from robustband.parsers import PARSE
from robustband.metrics import METRIC
from robustband.aggregate import AGG

DATA = os.path.join(ROOT, "demo", "data")
DATA_REAL = os.path.join(ROOT, "demo", "data_real")
RESULTS = os.path.join(ROOT, "results")

DEFAULT = ("strict_exact", "exact_match", "micro")
PARSES = list(PARSE); METRICS = list(METRIC); AGGS = list(AGG)

B_BOOT = 2000
SEED = 20261001


def load_jsonl(path, limit=None):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            rows.append((o.get("raw", ""), o.get("gold", ""), o.get("meta") or {}))
            if limit and len(rows) >= limit:
                break
    return rows


def band_of(preds, family, claim):
    b = evaluate(preds, family, claim)
    lo, hi = b.delta
    return b, lo, hi


# ══════════════════════════════════════════════════════════════════════
# P1 · 全量 n=1319 分数带（Q1：24 项 artifact？）
# ══════════════════════════════════════════════════════════════════════
def probe_p1():
    items = load_jsonl(os.path.join(DATA, "Qwen0.5B_cot.jsonl"))
    n = len(items)
    model = "Qwen2.5-0.5B-Instruct"
    preds = {model: {"items": items}}
    family = build_family()
    scores = {}
    for h in family:
        t = score_table(preds, h)
        scores[str(h)] = t[model]
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    width = hi - lo
    ratio = (hi / lo) if lo > 1e-12 else float("inf")
    # 哪个轴驱动带宽：分别固定两轴，看分数范围
    by_parse = {}
    for p in PARSES:
        vs = [v for k, v in scores.items() if k.split("|")[0] == p]
        by_parse[p] = (min(vs), max(vs))
    by_metric = {}
    for m in METRICS:
        vs = [v for k, v in scores.items() if k.split("|")[1] == m]
        by_metric[m] = (min(vs), max(vs))
    by_agg = {}
    for a in AGGS:
        vs = [v for k, v in scores.items() if k.split("|")[2] == a]
        by_agg[a] = (min(vs), max(vs))
    n_distinct = len(set(round(v, 9) for v in vals))
    ok = (width >= 0.10) and (ratio >= 3.0)
    return {
        "n": n, "model": model,
        "score_min": lo, "score_max": hi, "width": width, "ratio": ratio,
        "n_distinct_scores": n_distinct, "n_configs": len(family),
        "by_parse": by_parse, "by_metric": by_metric, "by_agg": by_agg,
        "score_min_arg": min(scores, key=scores.get),
        "score_max_arg": max(scores, key=scores.get),
        "G1-1_pass": ok,
    }


# ══════════════════════════════════════════════════════════════════════
# P2 · 逐项 bootstrap（Q2：只是这 24 项？）配对重采样
# ══════════════════════════════════════════════════════════════════════
def probe_p2():
    cot = load_jsonl(os.path.join(DATA_REAL, "cot.jsonl"))
    plain = load_jsonl(os.path.join(DATA_REAL, "plain.jsonl"))
    n = min(len(cot), len(plain))
    cot, plain = cot[:n], plain[:n]
    better, worse = "cot", "plain"
    claim = rb.RankClaim(better, worse, name="cot>plain")
    family = build_family()

    # 全样本基线
    base_preds = {better: {"items": cot}, worse: {"items": plain}}
    b0 = evaluate(base_preds, family, claim)

    rng = random.Random(SEED)
    compiled = CompiledScores(base_preds, family)
    n_unid = n_flip = 0
    stabs, los, his = [], [], []
    for _ in range(B_BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        b = compiled.evaluate(claim, idx)
        lo, hi = b.delta
        los.append(lo); his.append(hi); stabs.append(b.stability_fraction)
        if lo <= 0 <= hi:
            n_unid += 1
        if lo < 0 and hi > 0:
            n_flip += 1
    p_unid = n_unid / B_BOOT
    p_flip = n_flip / B_BOOT
    ok = (p_unid >= 0.90) and (p_flip >= 0.50)
    return {
        "n_items": n, "B": B_BOOT, "seed": SEED,
        "baseline_delta": b0.delta, "baseline_stability": b0.stability_fraction,
        "baseline_verdict": b0.verdict,
        "P_unidentifiable": p_unid, "P_signflip": p_flip,
        "stab_mean": sum(stabs) / len(stabs),
        "stab_min": min(stabs), "stab_max": max(stabs),
        "lo_mean": sum(los) / len(los), "hi_mean": sum(his) / len(his),
        "lo_max": max(los), "hi_min": min(his),
        "G1-2_pass": ok,
    }


# ══════════════════════════════════════════════════════════════════════
# P3 · ℋ 子族敏感性（Q3：只是某条怪配置？）
# ══════════════════════════════════════════════════════════════════════
def probe_p3():
    cot = load_jsonl(os.path.join(DATA_REAL, "cot.jsonl"))
    plain = load_jsonl(os.path.join(DATA_REAL, "plain.jsonl"))
    n = min(len(cot), len(plain))
    preds = {"cot": {"items": cot[:n]}, "plain": {"items": plain[:n]}}
    claim = rb.RankClaim("cot", "plain", name="cot>plain")

    # (a) 全族基线
    full = build_family()
    bf = evaluate(preds, full, claim)

    # (b) 留一轴值子族（13 个）
    leave_one = {}
    for axis, values, kw in [("parse", PARSES, "parses"),
                             ("metric", METRICS, "metrics"),
                             ("agg", AGGS, "aggs")]:
        for v in values:
            rest = [x for x in values if x != v]
            kwd = {kw: rest}
            fam = build_family(**kwd)
            b = evaluate(preds, fam, claim)
            lo, hi = b.delta
            leave_one[f"{axis}:{v}"] = {
                "n_configs": len(fam), "delta": b.delta, "verdict": b.verdict,
                "contains0": (lo <= 0 <= hi), "stability": b.stability_fraction,
            }
    all_contain0 = all(v["contains0"] for v in leave_one.values())

    # (c) 单轴子族（其余两轴钉在 DEFAULT）
    def single_axis(axis):
        kwd = {"parses": [DEFAULT[0]], "metrics": [DEFAULT[1]], "aggs": [DEFAULT[2]]}
        if axis == "parse":
            kwd["parses"] = PARSES
        elif axis == "metric":
            kwd["metrics"] = METRICS
        elif axis == "agg":
            kwd["aggs"] = AGGS
        fam = build_family(**kwd)
        b = evaluate(preds, fam, claim)
        return {"n_configs": len(fam), "delta": b.delta, "verdict": b.verdict,
                "margins": b.margins}
    single = {ax: single_axis(ax) for ax in ["parse", "metric", "agg"]}

    ok = all_contain0
    return {
        "n_items": n,
        "full_delta": bf.delta, "full_verdict": bf.verdict,
        "n_leave_one": len(leave_one), "all_contain0": all_contain0,
        "leave_one": leave_one,
        "single_axis": single,
        "G1-3_pass": ok,
    }


def main():
    print("=" * 72)
    print("C′ 主线 · Gate-1「现象站稳」包 (纯 CPU)")
    print("=" * 72)

    p1 = probe_p1()
    print("\n[P1] 全量 n=1319 分数带（Q1: 24 项 artifact?）")
    print(f"  n={p1['n']}  score∈[{p1['score_min']:.6f}, {p1['score_max']:.6f}]  "
          f"width={p1['width']:.6f}  ratio={p1['ratio']:.3f}  distinct={p1['n_distinct_scores']}")
    print(f"  min@ {p1['score_min_arg']}   max@ {p1['score_max_arg']}")
    print(f"  by_parse={ {k:(round(a,4),round(b,4)) for k,(a,b) in p1['by_parse'].items()} }")
    print(f"  by_metric={ {k:(round(a,4),round(b,4)) for k,(a,b) in p1['by_metric'].items()} }")
    print(f"  by_agg={ {k:(round(a,4),round(b,4)) for k,(a,b) in p1['by_agg'].items()} }")
    print(f"  G1-1 = {p1['G1-1_pass']}")

    p2 = probe_p2()
    print("\n[P2] 逐项 bootstrap（Q2: 只是这 24 项?）B=2000 配对重采样")
    print(f"  baseline δ={tuple(round(x,6) for x in p2['baseline_delta'])}  "
          f"stab={p2['baseline_stability']:.4f}  {p2['baseline_verdict']}")
    print(f"  P(UNIDENTIFIABLE)={p2['P_unidentifiable']:.4f}   P(sign-flip)={p2['P_signflip']:.4f}")
    print(f"  stab∈[{p2['stab_min']:.4f},{p2['stab_max']:.4f}] mean={p2['stab_mean']:.4f}  "
          f"lo_max={p2['lo_max']:.6f}  hi_min={p2['hi_min']:.6f}")
    print(f"  G1-2 = {p2['G1-2_pass']}")

    p3 = probe_p3()
    print("\n[P3] ℋ 子族敏感性（Q3: 只是某条怪配置?）")
    print(f"  full δ={tuple(round(x,6) for x in p3['full_delta'])}  {p3['full_verdict']}")
    print(f"  留一轴值子族 {p3['n_leave_one']} 个，全部仍含 0 = {p3['all_contain0']}")
    for k, v in p3["leave_one"].items():
        d = tuple(round(x, 6) for x in v["delta"])
        print(f"    -{k:24s} n={v['n_configs']:2d} δ={d} {v['verdict']:14s} contains0={v['contains0']}")
    for ax, v in p3["single_axis"].items():
        d = tuple(round(x, 6) for x in v["delta"])
        print(f"    单轴[{ax:7s}] n={v['n_configs']:2d} δ={d} {v['verdict']}")
    print(f"  G1-3 = {p3['G1-3_pass']}")

    passed = p1["G1-1_pass"] and p2["G1-2_pass"] and p3["G1-3_pass"]
    print("\n" + "=" * 72)
    print(f"判决: G1-1={p1['G1-1_pass']} ∧ G1-2={p2['G1-2_pass']} ∧ G1-3={p3['G1-3_pass']} "
          f"⟹ Gate-1 站稳 = {passed}")
    print("=" * 72)

    out = {"G1-1": p1, "G1-2": p2, "G1-3": p3,
           "gate1_standing": passed,
           "judgment": "PASS" if passed else "PARTIAL"}
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "gate1_standing_result.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n已写: results/gate1_standing_result.json")


if __name__ == "__main__":
    main()
