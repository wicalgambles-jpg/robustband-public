# SPDX-License-Identifier: MIT
"""E 负模块（核心负模块）：从 Band 抽取最小可复现反例 / 不可行性证书。
与 C′ 正面 δ-带同版本发布。
"""
from .core import score_table


def minimal_counterexample(preds, family, claim, band):
    """返回使主张翻转的、|margin| 最小的配置（最小反例），附复现所需信息。
    若 break_set 为空，返回 None。
    """
    if not band.break_set:
        return None
    best_key = min(band.break_set, key=lambda s: abs(band.margins[s]))
    h = next(x for x in family if str(x) == best_key)
    t = score_table(preds, h)
    return {
        "type": "minimal_counterexample",
        "config": best_key,
        "margin": band.margins[best_key],
        "table_under_config": t,
        "repro": {
            "parse": h.parse,
            "metric": h.metric,
            "agg": h.agg,
            "claim": claim.name,
            "claim_kind": claim.kind,
        },
    }


def impossibility_certificate(band):
    """严格主张同时有成立和不成立配置时签发；分别标注平局与严格反转。
    返回 None 若不适用。
    """
    lo, hi = band.delta
    if lo <= 0 < hi:
        strict_flip = lo < 0
        return {
            "type": "impossibility_certificate",
            "statement": (
                f"在 ℋ（{band.n_configs} 配置）内 δ∈[{lo:.6g}, {hi:.6g}] 含 0，" +
                ("存在合法配置给出严格相反方向。" if strict_flip else
                 "存在合法配置使严格主张成立或仅打平；未观察到反向胜出。")
            ),
            "delta": band.delta,
            "strict_sign_flip": strict_flip,
            "stability_fraction": band.stability_fraction,
            "witness_positive": _arg_extreme(band.margins, +1),
            "witness_negative": _arg_extreme(band.margins, -1),
        }
    return None


def _arg_extreme(margins, sign):
    if not margins:
        return None
    if sign > 0:
        k = max(margins, key=margins.get)
    else:
        k = min(margins, key=margins.get)
    return {"config": k, "margin": margins[k]}


def emit(preds, family, claim, band):
    """统一出口：优先给不可行性证书；否则给最小反例；都无则 None。"""
    c = impossibility_certificate(band)
    if c is not None:
        return c
    return minimal_counterexample(preds, family, claim, band)
