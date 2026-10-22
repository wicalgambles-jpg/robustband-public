# SPDX-License-Identifier: MIT
"""独立蛮力参考实现（S-C1 用）。
刻意不复用 robustband 包内任何函数：自带 parse/metric/agg，逐配置显式循环。
若与 robustband 逐项一致，则引擎正确性获得独立证据。
"""

# 控制台健壮性：Windows 传统控制台默认 GBK，无法编码中文/−/✔ 等字形会直接崩溃。
# 强制 UTF-8 输出（现代终端正确渲染；无法编码的字符以替代符输出，绝不崩溃）。
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import re
import statistics
from collections import Counter
from decimal import Decimal, InvalidOperation
from fractions import Fraction

_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def ref_parse(name, raw):
    raw = raw or ""
    if name == "strict_exact":
        return raw.strip()
    if name == "first_num":
        m = _NUM.search(raw)
        return m.group(0) if m else raw.strip()
    if name == "last_num":
        ms = _NUM.findall(raw)
        return ms[-1] if ms else raw.strip()
    if name == "last_line_num":
        lines = [l for l in raw.splitlines() if l.strip()]
        if not lines:
            return ""
        ms = _NUM.findall(lines[-1])
        return ms[-1] if ms else lines[-1].strip()
    if name == "boxed":
        m = re.search(r"\\boxed\{([^{}]*)\}", raw)
        if m:
            return m.group(1).strip()
        ms = _NUM.findall(raw)
        return ms[-1] if ms else raw.strip()
    raise ValueError(name)


def _norm(s):
    return re.sub(r"\s+", " ", str(s).strip()).lower()


def _number(s):
    try:
        value = Decimal(re.sub(r"[,\$%]", "", str(s).strip()))
        return Fraction(value) if value.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def ref_metric(name, cand, gold, tol=1e-3):
    if name == "exact_match":
        if _norm(cand) == _norm(gold):
            return 1
        fa, fg = _number(cand), _number(gold)
        if fa is not None and fg is not None and abs(fa - fg) <= Fraction(1, 10**9):
            return 1
        return 0
    if name == "contains":
        g = _norm(gold)
        return 1 if (g != "" and g in _norm(cand)) else 0
    if name == "f1_token":
        a, g = _norm(cand).split(), _norm(gold).split()
        if not a or not g:
            return 0
        ca, cg = Counter(a), Counter(g)
        ov = sum((ca & cg).values())
        if ov == 0:
            return 0
        return 1 if 4 * ov >= len(a) + len(g) else 0
    if name == "numeric_tol":
        fa, fg = _number(cand), _number(gold)
        if fa is not None and fg is not None:
            return 1 if abs(fa - fg) <= Fraction(Decimal(str(tol))) else 0
        return ref_metric("exact_match", cand, gold)
    raise ValueError(name)


def ref_agg(name, corrects, metas):
    if name == "micro":
        return sum(corrects) / len(corrects) if corrects else 0.0
    if name == "median":
        return statistics.median(corrects) if corrects else 0.0
    key = "class" if name == "macro_class" else ("len_bucket" if name == "macro_len" else None)
    if key is None:
        raise ValueError(name)
    groups = {}
    for c, m in zip(corrects, metas):
        k = (m or {}).get(key)
        if k is None:
            k = "__all__"
        groups.setdefault(k, []).append(c)
    if not groups:
        return 0.0
    return sum((sum(v) / len(v)) for v in groups.values()) / len(groups)


def ref_score_table(preds, p, m, a):
    out = {}
    for model, blob in preds.items():
        corrects, metas = [], []
        for raw, gold, meta in blob["items"]:
            corrects.append(ref_metric(m, ref_parse(p, raw), gold))
            metas.append(meta or {})
        out[model] = ref_agg(a, corrects, metas)
    return out


def ref_evaluate(preds, parses, metrics, aggs, claim_kind, claim_args):
    """返回 (stability_fraction, break_set(sorted), lo, hi, margins{key:val})。"""
    margins, breaks = {}, []
    for p in parses:
        for m in metrics:
            for a in aggs:
                key = f"{p}|{m}|{a}"
                t = ref_score_table(preds, p, m, a)
                if claim_kind == "rank":
                    better, worse = claim_args
                    marg = t[better] - t[worse]
                    ok = t[better] > t[worse]
                else:
                    model, thr = claim_args
                    marg = t[model] - thr
                    ok = t[model] > thr
                margins[key] = marg
                if not ok:
                    breaks.append(key)
    vals = list(margins.values())
    lo, hi = (min(vals), max(vals)) if vals else (0.0, 0.0)
    n = len(parses) * len(metrics) * len(aggs)
    stab = 1 - len(breaks) / n if n else 0.0
    return stab, sorted(breaks), lo, hi, margins
