# SPDX-License-Identifier: MIT
"""robustband.rational — 精确有理「认证带」（certified band）。

把 A 档（仅计分）的 δ 带从浮点升级为**精确有理**，作为可复用的一等能力：
  - 逐 item 对错 {0,1} 由 PARSE/METRIC 给出；数值比较以十进制有理数精确执行；
  - 聚合（micro / median / macro_class / macro_len）用 `Fraction` 精确计算；
  - 内建度量的有限十进制判定可精确计算；CERTAIN 为完整配置族；
  - **复制不变性**：item 复制 k 倍后端点 `Fraction` 逐位不变。

用途：`rational_band(...)` 给 (lo, hi) 的精确有理表示；`duplication_invariance(...)` 检查复制不变性。
与 `core.evaluate` 的关系：`float(rational_band().lo) == evaluate().delta[0]`（≤1e-12），
故可作为「同一带的精确版本」在证书中并列。
"""
from fractions import Fraction as F

from .parsers import PARSE
from .metrics import METRIC
from .core import build_family


def score_frac(corrects, metas, agg):
    """逐 item 对错(0/1) -> 精确有理总分。语义与 robustband.aggregate 一致。"""
    n = len(corrects)
    if n == 0:
        return F(0)
    if agg == "micro":
        return F(sum(corrects), n)
    if agg == "median":
        s = sorted(corrects)
        if n % 2 == 1:
            return F(s[n // 2])
        return F(s[n // 2 - 1] + s[n // 2], 2)
    key = {"macro_class": "class", "macro_len": "len_bucket"}[agg]
    groups = {}
    for c, m in zip(corrects, metas):
        k = (m or {}).get(key)
        if k is None:
            k = "__all__"
        groups.setdefault(k, []).append(c)
    per = [F(sum(v), len(v)) for v in groups.values()]
    return sum(per, F(0)) / len(per)


def item_correct_and_certain(items, parse_name, metric_name):
    """返回 (corrects 0/1 列表, certain)。
    内建度量使用十进制有理数或整数判定，因此所有配置都为 CERTAIN。
    """
    parse, metric = PARSE[parse_name], METRIC[metric_name]
    corrects = []
    for raw, gold, meta in items:
        cand = parse(raw)
        corrects.append(int(metric(cand, gold, meta)))
    return corrects, True


def rational_band(better_items, worse_items, family=None):
    """精确有理 δ 带（rank 主张 better>worse）。
    返回 dict：rows / lo / hi / lo_c / hi_c / n_certain / n_configs（端点皆 Fraction）。
    """
    fam = build_family() if family is None else family
    if not fam:
        raise ValueError("family must contain at least one configuration")
    rows = []
    for h in fam:
        bc, bcert = item_correct_and_certain(better_items, h.parse, h.metric)
        wc, wcert = item_correct_and_certain(worse_items, h.parse, h.metric)
        bs = score_frac(bc, [m for _, _, m in better_items], h.agg)
        ws = score_frac(wc, [m for _, _, m in worse_items], h.agg)
        rows.append((str(h), bs - ws, (bcert and wcert)))
    lo = min(r[1] for r in rows)
    hi = max(r[1] for r in rows)
    certain = [r for r in rows if r[2]]
    lo_c = min((r[1] for r in certain), default=None)
    hi_c = max((r[1] for r in certain), default=None)
    return {
        "rows": rows, "lo": lo, "hi": hi,
        "lo_c": lo_c, "hi_c": hi_c,
        "n_certain": len(certain), "n_configs": len(rows),
    }


def duplication_invariance(better_items, worse_items, ks=(1, 2, 4, 8), family=None):
    """复制不变性检查：item 复制 k 倍 ⟹ 端点 Fraction 逐位不变。
    返回 (base_band, reps)，reps[i]={"k","lo","hi","same"}。
    """
    base = rational_band(better_items, worse_items, family)
    reps = []
    for k in ks:
        b = rational_band(better_items * k, worse_items * k, family)
        reps.append({
            "k": k, "lo": b["lo"], "hi": b["hi"],
            "same": (b["lo"] == base["lo"] and b["hi"] == base["hi"]),
        })
    return base, reps


def frac_to_json(fr):
    """Fraction -> 可 JSON 化的 {num, den, float}（None 透传）。"""
    if fr is None:
        return None
    return {"num": fr.numerator, "den": fr.denominator, "float": float(fr)}
