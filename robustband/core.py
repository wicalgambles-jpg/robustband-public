# SPDX-License-Identifier: MIT
"""robustband 核心引擎：给定 (逐模型逐 item 原始输出, 扰动族 H, 主张 K)，
输出 K 的稳健带 Band（稳健比例 / 破坏集 / δ 带 / 判决 / 逐配置 margin）。
"""
from dataclasses import dataclass, field
from itertools import product

from .parsers import PARSE
from .metrics import METRIC
from .aggregate import AGG


@dataclass(frozen=True)
class Perturbation:
    parse: str
    metric: str
    agg: str

    def __str__(self):
        return f"{self.parse}|{self.metric}|{self.agg}"


def build_family(parses=None, metrics=None, aggs=None):
    """A 档扰动族：parse × metric × agg 的笛卡尔积。"""
    parses = list(PARSE) if parses is None else parses
    metrics = list(METRIC) if metrics is None else metrics
    aggs = list(AGG) if aggs is None else aggs
    return [Perturbation(p, m, a) for p, m, a in product(parses, metrics, aggs)]


def _prepare(preds, family):
    """Parse each item once per parse mode and score once per (parse, metric).

    The family is a product: 80 protocols share only 5 parse modes and 20
    (parse, metric) pairs, so scoring per protocol would repeat the same string
    work 16 and 4 times respectively. Returns (models, metas, correct).
    """
    pairs = sorted({(h.parse, h.metric) for h in family})
    parses = sorted({parse for parse, _ in pairs})
    models = list(preds)
    metas, candidates, correct = {}, {}, {}
    for model in models:
        items = preds[model]["items"]
        metas[model] = [meta or {} for _, _, meta in items]
        for name in parses:
            parse = PARSE[name]
            candidates[(model, name)] = [parse(raw) for raw, _, _ in items]
        for parse_name, metric_name in pairs:
            metric = METRIC[metric_name]
            correct[(model, parse_name, metric_name)] = [
                metric(cand, gold, meta)
                for cand, (_, gold, meta) in zip(candidates[(model, parse_name)], items)]
    return models, metas, correct


def _table(prepared, h):
    models, metas, correct = prepared
    agg = AGG[h.agg]
    return {model: agg(correct[(model, h.parse, h.metric)], metas[model]) for model in models}


def score_table(preds, h):
    """preds: {model: {"items": [(raw, gold, meta), ...]}}
    返回 {model: aggregated_score}。
    """
    return _table(_prepare(preds, [h]), h)


@dataclass
class Band:
    stability_fraction: float
    break_set: list
    delta: tuple
    verdict: str
    n_configs: int
    margins: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "stability_fraction": self.stability_fraction,
            "n_break": len(self.break_set),
            "n_configs": self.n_configs,
            "break_set": self.break_set,
            "delta": self.delta,
            "verdict": self.verdict,
            "margins": self.margins,
        }


def _verdict(lo, hi, stab):
    if hi <= 0:
        return "REFUTED"
    if lo > 0:
        return "ROBUST"
    return "UNIDENTIFIABLE"


def evaluate(preds, family, claim, tol_eps=0.0):
    """主入口。非零 tol_eps 尚无明确定义，显式拒绝以免静默误判。"""
    if tol_eps != 0.0:
        raise ValueError("nonzero tol_eps is unsupported; express the threshold in the claim")
    if not family:
        raise ValueError("family must contain at least one configuration")
    prepared = _prepare(preds, family)
    margins, breaks = {}, []
    for h in family:
        t = _table(prepared, h)
        m = claim.margin(t)
        key = str(h)
        margins[key] = m
        if not claim.holds(t):
            breaks.append(key)
    vals = list(margins.values())
    lo, hi = (min(vals), max(vals)) if vals else (0.0, 0.0)
    stab = 1 - len(breaks) / len(family) if family else 0.0
    return Band(stab, breaks, (lo, hi), _verdict(lo, hi, stab), len(family), margins)
