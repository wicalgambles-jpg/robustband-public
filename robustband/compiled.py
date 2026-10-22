# SPDX-License-Identifier: MIT
"""Experimental immutable scoring snapshot for repeated paired resampling.

Parsing and item metrics run once. Aggregators are captured from the registry
and run on each resample, retaining micro/macro/median semantics exactly.
"""
from copy import deepcopy

from .aggregate import AGG
from .core import Band, _verdict
from .metrics import METRIC
from .parsers import PARSE


class CompiledScores:
    """Freeze item scores and metadata; evaluate claims without rescoring text."""

    def __init__(self, preds, family):
        self.family = tuple(family)
        if not self.family:
            raise ValueError("family must contain at least one configuration")
        self._aggregators = {h.agg: AGG[h.agg] for h in self.family}
        pairs = tuple(dict.fromkeys((h.parse, h.metric) for h in self.family))
        parses = tuple(dict.fromkeys(p for p, _ in pairs))
        self._scores, self._metas, self._labels = {}, {}, {}
        for model, blob in preds.items():
            items = deepcopy(list(blob["items"]))
            self._labels[model] = tuple((gold, meta) for _, gold, meta in items)
            self._metas[model] = tuple(meta or {} for _, _, meta in items)
            candidates = {p: tuple(PARSE[p](raw) for raw, _, _ in items) for p in parses}
            self._scores[model] = {(p, m): tuple(METRIC[m](cand, gold, meta)
                for cand, (_, gold, meta) in zip(candidates[p], items)) for p, m in pairs}

    def evaluate(self, claim, indices=None):
        """Same Band as core.evaluate; indices may repeat but must be paired."""
        if indices is not None:
            indices = tuple(indices)
            lengths = {len(metas) for metas in self._metas.values()}
            if len(lengths) != 1:
                raise ValueError("paired resampling requires equal record lengths")
            labels = list(self._labels.values())
            if any(row != labels[0] for row in labels[1:]):
                raise ValueError("paired resampling requires aligned gold and metadata; check item IDs")
            n = next(iter(lengths))
            if any(type(i) is not int or not 0 <= i < n for i in indices):
                raise ValueError("resampling indices must be valid integer item positions")
        metas = {model: list(rows) if indices is None else [rows[i] for i in indices]
                 for model, rows in self._metas.items()}
        vectors = {model: {pair: list(row) if indices is None else [row[i] for i in indices]
                          for pair, row in scores.items()} for model, scores in self._scores.items()}
        margins, breaks = {}, []
        for h in self.family:
            table = {model: self._aggregators[h.agg](scores[(h.parse, h.metric)], metas[model])
                     for model, scores in vectors.items()}
            key, margin = str(h), claim.margin(table)
            margins[key] = margin
            if not claim.holds(table):
                breaks.append(key)
        lo, hi = min(margins.values()), max(margins.values())
        stab = 1 - len(breaks) / len(self.family)
        return Band(stab, breaks, (lo, hi), _verdict(lo, hi, stab), len(self.family), margins)
