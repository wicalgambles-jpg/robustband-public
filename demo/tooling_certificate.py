# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""C′+E 工具轨 · 统一「结论稳健带」证书（单份可运行仪器，纯 CPU，无生成，无 GPU）。

把四层绑定为**一份 JSON 证书** `results/tooling_certificate.json`：
  L1 正面 δ-带（C′ 仪器输出：ℋ=80 配置下主张的 δ 带 + 见证 + 判决）
  L2 负模块（E：不可行性证书 + 最小反例 + 最强反例 + 决策挂钩 D1/D2/D3）
  L3 现象稳健（Gate-1 三重：全量 n=1319 分带 + B=2000 逐项 bootstrap + 13 留一子族）
  L4 精确有理认证端点（Fraction lo/hi + 边界围栏 CERTAIN + 复制不变性）

契约（本文件即判据，跑后不改）：
  L1 与 L4 必须一致：float(rational.lo/hi) == engine.delta（≤1e-12）。
  L4 复制不变性：k∈{1,2,4,8} 端点 Fraction 逐位相等。
  L3 bootstrap：P(UNIDENTIFIABLE) ≥ 0.90 且 P(sign-flip) ≥ 0.50；13 留一子族全部仍含 0。
  overall = "PASS" ⟺ (L1 一致) ∧ (L2 至少一条负模块) ∧ (L3 三判据) ∧ (L4 一致+不可约)。
  本证书由 `verify_tooling_certificate.py` **独立复算**确认（不信任本文件的读数）。
"""
import os
import sys
import json
import random
import hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 控制台健壮性：Windows 传统控制台默认 GBK，无法编码 − / ✔ 等字形会直接崩溃。
# 强制 UTF-8 输出（现代终端正确渲染；无法编码的字符以替代符输出，绝不崩溃）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import robustband as rb  # noqa: E402
from robustband.compiled import CompiledScores  # noqa: E402
from robustband.core import build_family, score_table, evaluate  # noqa: E402
from robustband.parsers import PARSE  # noqa: E402
from robustband.metrics import METRIC  # noqa: E402
from robustband.aggregate import AGG  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DATA_REAL = os.path.join(HERE, "data_real")
RESULTS = os.path.join(ROOT, "results")

DEFAULT = "strict_exact|exact_match|micro"
PARSES, METRICS, AGGS = list(PARSE), list(METRIC), list(AGG)
B_BOOT, SEED = 2000, 20261001
SOURCE_FILES = {
    "items": os.path.join(DATA, "items.json"),
    "full_cot": os.path.join(DATA, "Qwen0.5B_cot.jsonl"),
    "paired_cot": os.path.join(DATA_REAL, "cot.jsonl"),
    "paired_plain": os.path.join(DATA_REAL, "plain.jsonl"),
}

DECISION_HOOK = {
    "D1_eval_authors": "据 δ-带在论文中显式声明该跨配置排名『在 ℋ 下稳健/脆弱』",
    "D2_bench_maintainers": "据 break_set 停止对不稳健指标的调参 / 增加检测项",
    "D3_reviewers": "据不可识别证书要求作者补跑或据以拒稿",
}


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


def source_manifest():
    """Bind the certificate to shipped bytes and check row-order alignment."""
    with open(SOURCE_FILES["items"], encoding="utf-8") as f:
        items = json.load(f)
    rows = {name: load_jsonl(path) for name, path in SOURCE_FILES.items() if name != "items"}
    expected = {"items": 1319, "full_cot": 1319, "paired_cot": 30, "paired_plain": 24}
    if len(items) != expected["items"]:
        raise ValueError("items.json does not contain the frozen 1319 items")
    for name, data in rows.items():
        if len(data) != expected[name]:
            raise ValueError(f"{name} row count changed: {len(data)}")
        if any((gold, meta) != (items[i]["gold"], items[i]["meta"])
               for i, (_, gold, meta) in enumerate(data)):
            raise ValueError(f"{name} is not aligned with items.json")
    manifest = {}
    for name, path in SOURCE_FILES.items():
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()
        manifest[name] = {"path": os.path.relpath(path, ROOT).replace("\\", "/"),
                          "sha256": digest, "n_rows": expected[name]}
    return manifest


# ── L1 正面 δ-带 ─────────────────────────────────────────────────────
def layer1():
    cot = load_jsonl(os.path.join(DATA_REAL, "cot.jsonl"))
    plain = load_jsonl(os.path.join(DATA_REAL, "plain.jsonl"))
    n = min(len(cot), len(plain))
    cot, plain = cot[:n], plain[:n]
    preds = {"cot": {"items": cot}, "plain": {"items": plain}}
    claim = rb.RankClaim("cot", "plain", name="cot>plain")
    family = build_family()
    b = evaluate(preds, family, claim)
    wp = max(b.margins, key=b.margins.get)
    wn = min(b.margins, key=b.margins.get)
    return {
        "n_items": n, "n_configs": b.n_configs,
        "delta": list(b.delta), "verdict": b.verdict,
        "stability_fraction": b.stability_fraction,
        "n_break": len(b.break_set),
        "witness_positive": {"config": wp, "margin": b.margins[wp]},
        "witness_negative": {"config": wn, "margin": b.margins[wn]},
        "default_margin": b.margins[DEFAULT],
    }, preds, claim, family


# ── L2 负模块（E） ───────────────────────────────────────────────────
def layer2(preds, family, claim):
    b = evaluate(preds, family, claim)
    imp = rb.certificate.impossibility_certificate(b)
    mce = rb.certificate.minimal_counterexample(preds, family, claim, b)
    neg = {k: v for k, v in b.margins.items() if v < 0}
    sce = None
    if neg:
        kmin = min(neg, key=neg.get)
        h = next(x for x in family if str(x) == kmin)
        sce = {"type": "strongest_counterexample", "config": kmin, "margin": neg[kmin],
               "table_under_config": score_table(preds, h)}
    return {
        "impossibility_certificate": imp,
        "minimal_counterexample": mce,
        "strongest_counterexample": sce,
        "decision_hook": DECISION_HOOK,
    }


# ── L3 现象稳健（Gate-1 三重） ───────────────────────────────────────
def layer3():
    # P1 全量 n=1319 分带
    items = load_jsonl(os.path.join(DATA, "Qwen0.5B_cot.jsonl"))
    model = "Qwen2.5-0.5B-Instruct"
    preds_full = {model: {"items": items}}
    fam = build_family()
    scores = {str(h): score_table(preds_full, h)[model] for h in fam}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    p1 = {
        "n": len(items), "model": model,
        "score_min": lo, "score_max": hi, "width": hi - lo,
        "score_ratio": (hi / lo if lo > 0 else None),
        "n_distinct_scores": len(set(round(v, 9) for v in vals)),
        "n_configs": len(fam),
        "min_config": min(scores, key=scores.get),
        "max_config": max(scores, key=scores.get),
    }
    p1["pass"] = (p1["width"] >= 0.10 and (lo == 0 or hi / lo >= 3.0))

    # P2 逐项 bootstrap（配对重采样）
    cot = load_jsonl(os.path.join(DATA_REAL, "cot.jsonl"))
    plain = load_jsonl(os.path.join(DATA_REAL, "plain.jsonl"))
    n = min(len(cot), len(plain))
    cot, plain = cot[:n], plain[:n]
    claim = rb.RankClaim("cot", "plain", name="cot>plain")
    rng = random.Random(SEED)
    compiled = CompiledScores({"cot": {"items": cot}, "plain": {"items": plain}}, fam)
    n_unid = n_flip = 0
    stabs = []
    for _ in range(B_BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        bb = compiled.evaluate(claim, idx)
        l, h = bb.delta
        stabs.append(bb.stability_fraction)
        if l <= 0 <= h:
            n_unid += 1
        if l < 0 and h > 0:
            n_flip += 1
    p2 = {
        "B": B_BOOT, "seed": SEED, "n_items": n,
        "P_unidentifiable": n_unid / B_BOOT, "P_signflip": n_flip / B_BOOT,
        "stab_mean": sum(stabs) / len(stabs), "stab_min": min(stabs), "stab_max": max(stabs),
    }
    p2["pass"] = (p2["P_unidentifiable"] >= 0.90) and (p2["P_signflip"] >= 0.50)

    # P3 ℋ 子族敏感性（留一轴值 13 个 + 单轴 3 个）
    preds = {"cot": {"items": cot}, "plain": {"items": plain}}
    leave = {}
    for axis, values, kw in [("parse", PARSES, "parses"),
                             ("metric", METRICS, "metrics"),
                             ("agg", AGGS, "aggs")]:
        for v in values:
            rest = [x for x in values if x != v]
            f = build_family(**{kw: rest})
            bb = evaluate(preds, f, claim)
            l, h = bb.delta
            leave[f"{axis}:{v}"] = {"n_configs": len(f), "delta": [l, h],
                                    "verdict": bb.verdict, "contains0": (l <= 0 <= h)}
    single = {}
    for ax in ("parse", "metric", "agg"):
        kwd = {"parses": [PARSES[0]] if ax != "parse" else PARSES,
               "metrics": [METRICS[0]] if ax != "metric" else METRICS,
               "aggs": [AGGS[0]] if ax != "agg" else AGGS}
        # 其余两轴钉在冻结默认
        kwd = {"parses": [DEFAULT.split("|")[0]], "metrics": [DEFAULT.split("|")[1]],
               "aggs": [DEFAULT.split("|")[2]]}
        if ax == "parse":
            kwd["parses"] = PARSES
        elif ax == "metric":
            kwd["metrics"] = METRICS
        else:
            kwd["aggs"] = AGGS
        f = build_family(**kwd)
        bb = evaluate(preds, f, claim)
        single[ax] = {"n_configs": len(f), "delta": list(bb.delta), "verdict": bb.verdict}
    all_contain0 = all(x["contains0"] for x in leave.values())
    p3 = {"n_leave_one": len(leave), "all_contain0": all_contain0,
          "leave_one": leave, "single_axis": single}
    p3["pass"] = all_contain0

    return {"full_scale": p1, "bootstrap": p2, "subfamily": p3,
            "L3_pass": p1["pass"] and p2["pass"] and p3["pass"]}


# ── L4 精确有理认证端点 ──────────────────────────────────────────────
def layer4():
    cot = load_jsonl(os.path.join(DATA_REAL, "cot.jsonl"))
    plain = load_jsonl(os.path.join(DATA_REAL, "plain.jsonl"))
    n = min(len(cot), len(plain))
    cot, plain = cot[:n], plain[:n]
    base, reps = rb.rational.duplication_invariance(cot, plain, ks=(1, 2, 4, 8))
    lo, hi = base["lo"], base["hi"]
    return {
        "n_items": n, "n_configs": base["n_configs"],
        "band_all": {"lo": rb.rational.frac_to_json(lo), "hi": rb.rational.frac_to_json(hi)},
        "band_certain": {"lo": rb.rational.frac_to_json(base["lo_c"]),
                         "hi": rb.rational.frac_to_json(base["hi_c"])},
        "n_certain": base["n_certain"],
        "contains_zero": bool(lo <= 0 <= hi),
        "dup_reps": [{"k": r["k"], "lo": rb.rational.frac_to_json(r["lo"]),
                      "hi": rb.rational.frac_to_json(r["hi"]), "same": r["same"]} for r in reps],
        "dup_invariant": all(r["same"] for r in reps),
    }


def main():
    print("=" * 74)
    print("C′+E 工具轨 · 统一「结论稳健带」证书（纯 CPU）")
    print("=" * 74)
    sources = source_manifest()
    l1, preds, claim, family = layer1()
    l2 = layer2(preds, family, claim)
    l3 = layer3()
    l4 = layer4()

    # L1×L4 一致性（float 端点 vs 精确有理端点）
    lo_f = l4["band_all"]["lo"]["float"]
    hi_f = l4["band_all"]["hi"]["float"]
    l1_l4_consistent = (abs(lo_f - l1["delta"][0]) < 1e-12) and (abs(hi_f - l1["delta"][1]) < 1e-12)

    l2_ok = (l1["delta"][0] < 0 < l1["delta"][1]
             and l2["impossibility_certificate"] is not None
             and l2["minimal_counterexample"] is not None
             and l2["strongest_counterexample"] is not None)
    l4_ok = (l1_l4_consistent and l4["dup_invariant"]
             and l4["n_certain"] == l4["n_configs"]
             and l4["band_certain"] == l4["band_all"])
    overall = "PASS" if (l1_l4_consistent and l2_ok and l3["L3_pass"] and l4_ok) else "PARTIAL"

    print(f"\n[L1] 正面 δ-带  n={l1['n_items']} n_configs={l1['n_configs']}")
    print(f"     δ=({l1['delta'][0]:+.6f},{l1['delta'][1]:+.6f})  {l1['verdict']}  "
          f"stab={l1['stability_fraction']:.4f}  break={l1['n_break']}/{l1['n_configs']}")
    print(f"     见证[+] {l1['witness_positive']['config']} {l1['witness_positive']['margin']:+.6f}")
    print(f"     见证[−] {l1['witness_negative']['config']} {l1['witness_negative']['margin']:+.6f}")
    print(f"[L2] 负模块 不可行证书={'✔' if l2['impossibility_certificate'] else '—'}  "
          f"最小反例={'✔' if l2['minimal_counterexample'] else '—'}  "
          f"最强反例={'✔' if l2['strongest_counterexample'] else '—'}")
    print(f"[L3] 现象稳健 full width={l3['full_scale']['width']:.4f} (n={l3['full_scale']['n']}) | "
          f"P(unid)={l3['bootstrap']['P_unidentifiable']:.4f} P(flip)={l3['bootstrap']['P_signflip']:.4f} | "
          f"留一 {l3['subfamily']['n_leave_one']} 全含0={l3['subfamily']['all_contain0']}  -> L3={l3['L3_pass']}")
    print(f"[L4] 认证端点 δ=({l4['band_all']['lo']['num']}/{l4['band_all']['lo']['den']}, "
          f"{l4['band_all']['hi']['num']}/{l4['band_all']['hi']['den']})  "
          f"CERTAIN={l4['n_certain']}/{l4['n_configs']}  dup不变={l4['dup_invariant']}")
    print(f"     L1×L4 一致={l1_l4_consistent}")
    print("\n" + "=" * 74)
    print(f"overall = {overall}")
    print("=" * 74)

    cert = {
        "schema": "robustband.tooling_certificate/v2",
        "robustband_version": rb.__version__,
        "data_sources": sources,
        "claim": {"kind": claim.kind, "better": claim.better, "worse": claim.worse, "name": claim.name},
        "frozen_protocol": DEFAULT,
        "family_axes": {"parse": PARSES, "metric": METRICS, "agg": AGGS},
        "L1_positive_band": l1,
        "L2_negative_module": l2,
        "L3_robustness": l3,
        "L4_certified_endpoints": l4,
        "checks": {"L1_L4_consistent": l1_l4_consistent, "L2_has_negative_module": l2_ok,
                   "L3_pass": l3["L3_pass"], "L4_ok": l4_ok},
        "overall": overall,
        "repro": {
            "cert_cmd": "python tooling_certificate.py",
            "verify_cmd": "python verify_tooling_certificate.py",
        },
    }
    os.makedirs(RESULTS, exist_ok=True)
    op = os.path.join(RESULTS, "tooling_certificate.json")
    with open(op, "w", encoding="utf-8") as f:
        json.dump(cert, f, ensure_ascii=False, indent=2)
    print(f"[written] {op}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
