# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""精确有理认证带：与浮点路径一致、复制不变性、Fraction 端点。"""
from fractions import Fraction as F

import robustband as rb
from robustband.metrics import m_exact, m_numeric_tol


def test_rational_band_endpoints(flip_items):
    cot, plain = flip_items
    fam = rb.build_family(parses=["first_num", "last_num"],
                          metrics=["exact_match"], aggs=["micro"])
    r = rb.rational.rational_band(cot, plain, fam)
    assert r["lo"] == F(-1)
    assert r["hi"] == F(1)
    assert r["n_configs"] == 2


def test_rational_matches_float_full_family(flip_preds, flip_items):
    cot, plain = flip_items
    fam = rb.build_family()
    b = rb.evaluate(flip_preds, fam, rb.RankClaim("cot", "plain"))
    r = rb.rational.rational_band(cot, plain, fam)
    # 证书契约：float(精确端点) == engine.delta（≤1e-12）
    assert abs(float(r["lo"]) - b.delta[0]) < 1e-12
    assert abs(float(r["hi"]) - b.delta[1]) < 1e-12


def test_duplication_invariance(flip_items):
    cot, plain = flip_items
    fam = rb.build_family(parses=["first_num", "last_num"],
                          metrics=["exact_match"], aggs=["micro"])
    base, reps = rb.rational.duplication_invariance(cot, plain, ks=(1, 2, 4, 8), family=fam)
    assert base["lo"] == F(-1) and base["hi"] == F(1)
    assert [r["k"] for r in reps] == [1, 2, 4, 8]
    assert all(r["same"] for r in reps)


def test_micro_is_exact_fraction():
    # better 2/3，worse 1/3 ⟹ margin = 1/3（精确有理，非浮点近似）
    better = [("1", "1", {}), ("2", "2", {}), ("x", "3", {})]
    worse = [("1", "1", {}), ("x", "2", {}), ("x", "3", {})]
    fam = rb.build_family(parses=["last_num"], metrics=["exact_match"], aggs=["micro"])
    r = rb.rational.rational_band(better, worse, fam)
    assert r["lo"] == F(1, 3)
    assert r["hi"] == F(1, 3)


def test_score_frac_median():
    # 4 个对错 [1,1,1,0] 的中位数 = 1.0
    s = rb.rational.score_frac([1, 1, 1, 0], [{}] * 4, "median")
    assert s == F(1)
    # [1,0,0,0] 中位数 = 0.0
    s2 = rb.rational.score_frac([1, 0, 0, 0], [{}] * 4, "median")
    assert s2 == F(0)


def test_frac_to_json():
    d = rb.rational.frac_to_json(F(13, 200))
    assert d["num"] == 13 and d["den"] == 200
    assert abs(d["float"] - 0.065) < 1e-12
    assert rb.rational.frac_to_json(None) is None


def test_large_integer_comparison_is_exact():
    a, b = "9007199254740992", "9007199254740993"
    assert m_exact(a, b) == 0
    assert m_numeric_tol(a, b) == 0
    assert m_exact(a, a) == 1
    assert rb.rational.item_correct_and_certain([(a, b, {})], "strict_exact", "exact_match") == ([0], True)


def test_numeric_tolerance_decimal_boundary():
    assert m_numeric_tol("1.001", "1", tol=1e-3) == 1
    assert m_numeric_tol("1.0010000000000000001", "1", tol=1e-3) == 0
