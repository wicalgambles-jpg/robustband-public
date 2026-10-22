# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""独立复算校验：读 results/tooling_certificate.json，**不信任**其中读数，
用 robustband 引擎 + rational 模块从原始数据重算，逐层核对。
  V0 L1 引擎带复现（δ、判决、break 数）。
  V1 最小反例确实翻转（holds=False 且 margin 与证书一致）。
  V1b 最强反例 margin<0（真·反转）且与证书一致。
  V2 不可行性证书 δ⊇0；见证[+]为全族 argmax、见证[−]为 argmin。
  V3 自洽：stab == 1 − |break|/n_configs。
  V4 认证端点精确有理且等于 (−1/24, 13/200)；CERTAIN==80；float 与引擎一致。
  V5 复制不变性：k∈{1,2,4,8} 端点 Fraction 逐位相等（独立重算）。
  V6 逐项 bootstrap（同 seed）P(unid)/P(flip) 与证书一致。
  V7 13 个留一子族全部仍含 0。
任一不符 ⟹ 退出码 2。

用法：python verify_tooling_certificate.py
"""
import os
import sys
import json
import random
import hashlib
from fractions import Fraction as F

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
from ref_impl import ref_evaluate, ref_score_table  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DATA_REAL = os.path.join(HERE, "data_real")
CERT = os.path.join(ROOT, "results", "tooling_certificate.json")

DEFAULT = "strict_exact|exact_match|micro"
SOURCE_FILES = {
    "items": os.path.join(DATA, "items.json"),
    "full_cot": os.path.join(DATA, "Qwen0.5B_cot.jsonl"),
    "paired_cot": os.path.join(DATA_REAL, "cot.jsonl"),
    "paired_plain": os.path.join(DATA_REAL, "plain.jsonl"),
}


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            rows.append((o.get("raw", ""), o.get("gold", ""), o.get("meta") or {}))
    return rows


def verify_sources(cert):
    """Recheck the frozen files and row order without trusting artifact paths."""
    with open(SOURCE_FILES["items"], encoding="utf-8") as f:
        items = json.load(f)
    expected = {"items": 1319, "full_cot": 1319, "paired_cot": 30, "paired_plain": 24}
    if len(items) != expected["items"]:
        return False
    manifest = cert.get("data_sources", {})
    if set(manifest) != set(SOURCE_FILES):
        return False
    for name, path in SOURCE_FILES.items():
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()
        row = manifest[name]
        if row != {"path": os.path.relpath(path, ROOT).replace("\\", "/"),
                   "sha256": digest, "n_rows": expected[name]}:
            return False
        if name != "items":
            data = load_jsonl(path)
            if len(data) != expected[name] or any(
                (gold, meta) != (items[i]["gold"], items[i]["meta"])
                for i, (_, gold, meta) in enumerate(data)
            ):
                return False
    return True


def main():
    cert = json.load(open(CERT, encoding="utf-8"))
    fails = []

    vsource = (cert.get("schema") == "robustband.tooling_certificate/v2"
               and cert.get("robustband_version") == rb.__version__
               and verify_sources(cert))
    print(f"V-source 数据哈希、行数和题目对齐={vsource} -> {'PASS' if vsource else 'FAIL'}")
    if not vsource:
        fails.append("V-source")

    cot = load_jsonl(os.path.join(DATA_REAL, "cot.jsonl"))
    plain = load_jsonl(os.path.join(DATA_REAL, "plain.jsonl"))
    n = 24
    preds = {"cot": {"items": cot[:n]}, "plain": {"items": plain[:n]}}
    claim = rb.RankClaim("cot", "plain", name="cot>plain")
    family = build_family()
    b = evaluate(preds, family, claim)
    parses, metrics, aggs = list(rb.PARSE), list(rb.METRIC), list(rb.AGG)
    ref_stab, ref_breaks, ref_lo, ref_hi, ref_margins = ref_evaluate(
        preds, parses, metrics, aggs, "rank", ("cot", "plain"))

    # V0 L1 引擎带复现
    l1 = cert["L1_positive_band"]
    ok = (abs(b.delta[0] - l1["delta"][0]) < 1e-12 and abs(b.delta[1] - l1["delta"][1]) < 1e-12
          and b.verdict == l1["verdict"] and len(b.break_set) == l1["n_break"]
          and b.n_configs == l1["n_configs"] == 80 and l1["n_items"] == n
          and abs(b.stability_fraction - l1["stability_fraction"]) < 1e-12
          and abs(l1["default_margin"] - b.margins[DEFAULT]) < 1e-12
          and l1["witness_positive"]["config"] == max(b.margins, key=b.margins.get)
          and l1["witness_negative"]["config"] == min(b.margins, key=b.margins.get)
          and abs(l1["witness_positive"]["margin"] - max(b.margins.values())) < 1e-12
          and abs(l1["witness_negative"]["margin"] - min(b.margins.values())) < 1e-12
          and abs(ref_lo - b.delta[0]) < 1e-12 and abs(ref_hi - b.delta[1]) < 1e-12
          and abs(ref_stab - b.stability_fraction) < 1e-12
          and ref_breaks == sorted(b.break_set)
          and all(abs(ref_margins[k] - v) < 1e-12 for k, v in b.margins.items())
          and cert.get("family_axes") == {"parse": parses, "metric": metrics, "agg": aggs}
          and cert.get("frozen_protocol") == DEFAULT
          and cert.get("claim") == {"kind": "rank", "better": "cot", "worse": "plain", "name": "cot>plain"})
    print(f"V0 L1 引擎带  δ=({b.delta[0]:+.6f},{b.delta[1]:+.6f}) {b.verdict} "
          f"break={len(b.break_set)} -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        fails.append("V0")

    # V1 最小反例
    l2 = cert["L2_negative_module"]
    mce = l2["minimal_counterexample"]
    if mce is None:
        print("V1 [FAIL] 证书缺最小反例")
        fails.append("V1")
    else:
        h = rb.Perturbation(*mce["config"].split("|"))
        t = score_table(preds, h)
        holds = claim.holds(t)
        m = claim.margin(t)
        min_key = min(b.break_set, key=lambda k: abs(b.margins[k]))
        ok = ((not holds) and mce["config"] == min_key
              and abs(m - mce["margin"]) < 1e-12
              and all(abs(t[k] - v) < 1e-12 for k, v in mce["table_under_config"].items()))
        print(f"V1 最小反例 {mce['config']}: holds={holds} margin={m:+.6f} -> {'PASS' if ok else 'FAIL'}")
        if not ok:
            fails.append("V1")

    # V1b 最强反例
    sce = l2["strongest_counterexample"]
    if sce is None:
        print("V1b [FAIL] 证书缺严格反转见证")
        fails.append("V1b")
    else:
        h = rb.Perturbation(*sce["config"].split("|"))
        t = score_table(preds, h)
        m = claim.margin(t)
        neg = {k: v for k, v in b.margins.items() if v < 0}
        ok = ((not claim.holds(t)) and (m < 0) and sce["config"] == min(neg, key=neg.get)
              and abs(m - sce["margin"]) < 1e-12
              and all(abs(t[k] - v) < 1e-12 for k, v in sce["table_under_config"].items()))
        print(f"V1b 最强反例 {sce['config']}: margin={m:+.6f} -> {'PASS' if ok else 'FAIL'}")
        if not ok:
            fails.append("V1b")

    # V2 不可行性证书
    imp = l2["impossibility_certificate"]
    if imp is None:
        print("V2 [FAIL] 证书缺不可行性证书")
        fails.append("V2")
    else:
        lo, hi = b.delta
        argmax = max(b.margins, key=b.margins.get)
        argmin = min(b.margins, key=b.margins.get)
        ok = (lo < 0 < hi) and (imp["witness_positive"]["config"] == argmax) \
            and (imp["witness_negative"]["config"] == argmin) \
            and abs(imp["witness_positive"]["margin"] - b.margins[argmax]) < 1e-12 \
            and abs(imp["witness_negative"]["margin"] - b.margins[argmin]) < 1e-12 \
            and imp["strict_sign_flip"] is True \
            and all(abs(x-y) < 1e-12 for x, y in zip(imp["delta"], b.delta))
        print(f"V2 不可识别 δ=({lo:+.6f},{hi:+.6f}) 含0={lo<=0<=hi} "
              f"见证[+]{'✔' if imp['witness_positive']['config']==argmax else '✘'} "
              f"见证[−]{'✔' if imp['witness_negative']['config']==argmin else '✘'} -> {'PASS' if ok else 'FAIL'}")
        if not ok:
            fails.append("V2")

    # V3 自洽
    stab_ok = abs(b.stability_fraction - (1 - len(b.break_set) / b.n_configs)) < 1e-12
    stab_ok = stab_ok and abs(b.stability_fraction - l1["stability_fraction"]) < 1e-12
    print(f"V3 自洽 stab={b.stability_fraction:.4f} -> {'PASS' if stab_ok else 'FAIL'}")
    if not stab_ok:
        fails.append("V3")

    # V4 认证端点（精确有理）
    base, reps = rb.rational.duplication_invariance(cot[:n], plain[:n], ks=(1, 2, 4, 8))
    l4 = cert["L4_certified_endpoints"]
    lo_ok = (base["lo"] == F(-1, 24)) and (base["hi"] == F(13, 200))
    cert_ok = (l4["band_all"]["lo"]["num"] == base["lo"].numerator
               and l4["band_all"]["lo"]["den"] == base["lo"].denominator
               and l4["band_all"]["lo"]["float"] == float(base["lo"])
               and l4["band_all"]["hi"]["num"] == base["hi"].numerator
               and l4["band_all"]["hi"]["den"] == base["hi"].denominator
               and l4["band_all"]["hi"]["float"] == float(base["hi"]))
    certain_ok = (base["n_certain"] == l4["n_certain"] == 80
                  and l4["band_certain"] == l4["band_all"]
                  and l4["n_configs"] == 80 and l4["n_items"] == n
                  and l4["contains_zero"] is True)
    float_ok = (abs(float(base["lo"]) - b.delta[0]) < 1e-12 and abs(float(base["hi"]) - b.delta[1]) < 1e-12)
    v4 = lo_ok and cert_ok and certain_ok and float_ok
    print(f"V4 认证端点 δ=({base['lo']},{base['hi']}) == (-1/24,13/200)={lo_ok} "
          f"CERTAIN={base['n_certain']} float一致={float_ok} -> {'PASS' if v4 else 'FAIL'}")
    if not v4:
        fails.append("V4")

    # V5 复制不变性
    v5 = (all(r["same"] for r in reps) and l4["dup_invariant"] is True
          and l4["dup_reps"] == [
              {"k": r["k"], "lo": rb.rational.frac_to_json(r["lo"]),
               "hi": rb.rational.frac_to_json(r["hi"]), "same": r["same"]}
              for r in reps])
    print(f"V5 复制不变 k=1,2,4,8 端点逐位相等={v5} -> {'PASS' if v5 else 'FAIL'}")
    if not v5:
        fails.append("V5")

    # V6 full-scale: reference implementation, independent of robustband scoring.
    l3 = cert["L3_robustness"]
    full = load_jsonl(SOURCE_FILES["full_cot"])
    full_preds = {"Qwen2.5-0.5B-Instruct": {"items": full}}
    scores = {str(h): ref_score_table(full_preds, h.parse, h.metric, h.agg)["Qwen2.5-0.5B-Instruct"]
              for h in family}
    vals = list(scores.values())
    p1 = l3["full_scale"]
    full_expected = {"n": len(full), "model": "Qwen2.5-0.5B-Instruct",
                     "score_min": min(vals), "score_max": max(vals),
                     "width": max(vals) - min(vals),
                     "score_ratio": max(vals) / min(vals) if min(vals) > 0 else None,
                     "n_distinct_scores": len(set(round(v, 9) for v in vals)),
                     "n_configs": len(family),
                     "min_config": min(scores, key=scores.get),
                     "max_config": max(scores, key=scores.get),
                     "pass": (max(vals) - min(vals) >= 0.10
                              and (min(vals) == 0 or max(vals) / min(vals) >= 3.0))}
    v6 = (set(p1) == set(full_expected) and all(
        abs(p1[k] - v) < 1e-12 if type(v) is float else p1[k] == v
        for k, v in full_expected.items()))
    print(f"V6 全量 1319 题分数带 width={full_expected['width']:.4f} -> {'PASS' if v6 else 'FAIL'}")
    if not v6:
        fails.append("V6")

    # V7 bootstrap with frozen B and seed, not values supplied by the artifact.
    rng = random.Random(20261001)
    compiled = CompiledScores(preds, family)
    n_unid = n_flip = 0
    stabs = []
    for _ in range(2000):
        idx = [rng.randrange(n) for _ in range(n)]
        bb = compiled.evaluate(claim, idx)
        l, h = bb.delta
        stabs.append(bb.stability_fraction)
        if l <= 0 <= h:
            n_unid += 1
        if l < 0 and h > 0:
            n_flip += 1
    pu, pf = n_unid / 2000, n_flip / 2000
    p2 = l3["bootstrap"]
    v7 = (p2["B"] == 2000 and p2["seed"] == 20261001 and p2["n_items"] == n
          and abs(pu - p2["P_unidentifiable"]) < 1e-12
          and abs(pf - p2["P_signflip"]) < 1e-12
          and abs(sum(stabs)/len(stabs) - p2["stab_mean"]) < 1e-12
          and min(stabs) == p2["stab_min"] and max(stabs) == p2["stab_max"]
          and p2["pass"] == (pu >= 0.90 and pf >= 0.50))
    print(f"V7 bootstrap P(unid)={pu:.4f} P(flip)={pf:.4f} -> {'PASS' if v7 else 'FAIL'}")
    if not v7:
        fails.append("V7")

    # V8 leave-one-axis and single-axis fields.
    from robustband.parsers import PARSE
    from robustband.metrics import METRIC
    from robustband.aggregate import AGG
    allc = True
    leave = {}
    for axis, values, kw in [("parse", list(PARSE), "parses"),
                             ("metric", list(METRIC), "metrics"),
                             ("agg", list(AGG), "aggs")]:
        for v in values:
            f = build_family(**{kw: [x for x in values if x != v]})
            bb = evaluate(preds, f, claim)
            contains = bb.delta[0] <= 0 <= bb.delta[1]
            leave[f"{axis}:{v}"] = {"n_configs": len(f), "delta": list(bb.delta),
                                    "verdict": bb.verdict, "contains0": contains}
            allc = allc and contains
    single = {}
    for ax in ("parse", "metric", "agg"):
        kwd = {"parses": ["strict_exact"], "metrics": ["exact_match"], "aggs": ["micro"]}
        kwd[{"parse": "parses", "metric": "metrics", "agg": "aggs"}[ax]] = {
            "parse": parses, "metric": metrics, "agg": aggs}[ax]
        f = build_family(**kwd)
        bb = evaluate(preds, f, claim)
        single[ax] = {"n_configs": len(f), "delta": list(bb.delta), "verdict": bb.verdict}
    p3 = l3["subfamily"]
    v8 = (p3 == {"n_leave_one": 13, "all_contain0": allc,
                 "leave_one": leave, "single_axis": single, "pass": allc})
    print(f"V8 留一 13 子族与单轴读数一致={v8} -> {'PASS' if v8 else 'FAIL'}")
    if not v8:
        fails.append("V8")

    # Verify the decision, rather than merely printing the artifact's claim.
    checks = {"L1_L4_consistent": float_ok,
              "L2_has_negative_module": (b.delta[0] < 0 < b.delta[1]
                                         and imp is not None and mce is not None and sce is not None),
              "L3_pass": p1["pass"] and p2["pass"] and p3["pass"],
              "L4_ok": float_ok and v5 and certain_ok}
    voverall = (cert.get("checks") == checks
                and cert.get("overall") == ("PASS" if all(checks.values()) else "PARTIAL")
                and all(checks.values()))
    print(f"V-overall 证书决策与核验一致={voverall} -> {'PASS' if voverall else 'FAIL'}")
    if not voverall:
        fails.append("V-overall")
    if fails:
        print(f"\n[VERIFY FAIL] {fails}")
        return 2
    print("\n[VERIFY PASS] 统一证书可独立复现（L1–L4 全一致）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
        print(f"[VERIFY FAIL] invalid certificate or missing input: {exc}")
        raise SystemExit(2)
