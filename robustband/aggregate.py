# SPDX-License-Identifier: MIT
"""聚合轴（agg）：逐 item 对错向量 -> 标量总分。
沿 A 档（仅计分）冻结的 4 种合法聚合协议。
macro_* 在缺 meta 键时自动退化到 micro（全样本）。
"""
import statistics


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _macro(corrects, metas, key):
    groups = {}
    for c, m in zip(corrects, metas):
        k = (m or {}).get(key)
        if k is None:
            k = "__all__"
        groups.setdefault(k, []).append(c)
    return _mean([_mean(v) for v in groups.values()])


def a_micro(corrects, metas):
    return _mean(corrects)


def a_macro_class(corrects, metas):
    return _macro(corrects, metas, "class")


def a_macro_len(corrects, metas):
    return _macro(corrects, metas, "len_bucket")


def a_median(corrects, metas):
    return statistics.median(corrects) if corrects else 0.0


AGG = {
    "micro": a_micro,
    "macro_class": a_macro_class,
    "macro_len": a_macro_len,
    "median": a_median,
}
