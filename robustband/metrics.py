# SPDX-License-Identifier: MIT
"""度量轴（metric）：把 (candidate, gold) 判为对/错 {0,1}。
沿 A 档（仅计分）冻结的 4 种合法判对协议。
"""
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from functools import lru_cache


def _norm(s):
    return re.sub(r"\s+", " ", str(s).strip()).lower()


def _to_fraction(s):
    return _parse_numeric(str(s).strip())


@lru_cache(maxsize=16384)
def _parse_numeric(text):
    try:
        value = Decimal(re.sub(r"[,\$%]", "", text))
        return Fraction(value) if value.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


@lru_cache(maxsize=32)
def _tol_fraction(tol):
    return Fraction(Decimal(str(tol)))


def m_exact(cand, gold, meta=None, tol=1e-3):
    a, g = _norm(cand), _norm(gold)
    if a == g:
        return 1
    fa, fg = _to_fraction(cand), _to_fraction(gold)
    if fa is not None and fg is not None and abs(fa - fg) <= Fraction(1, 10**9):
        return 1
    return 0


def m_contains(cand, gold, meta=None, tol=1e-3):
    g = _norm(gold)
    return 1 if (g != "" and g in _norm(cand)) else 0


def m_f1_token(cand, gold, meta=None, tol=1e-3):
    a, g = _norm(cand).split(), _norm(gold).split()
    if not a or not g:
        return 0
    ca, cg = Counter(a), Counter(g)
    overlap = sum((ca & cg).values())
    if overlap == 0:
        return 0
    # F1 = 2*overlap/(len(a)+len(g)); compare to 1/2 exactly.
    return 1 if 4 * overlap >= len(a) + len(g) else 0


def m_numeric_tol(cand, gold, meta=None, tol=1e-3):
    fa, fg = _to_fraction(cand), _to_fraction(gold)
    if fa is not None and fg is not None:
        return 1 if abs(fa - fg) <= _tol_fraction(tol) else 0
    return m_exact(cand, gold)


METRIC = {
    "exact_match": m_exact,
    "contains": m_contains,
    "f1_token": m_f1_token,
    "numeric_tol": m_numeric_tol,
}
