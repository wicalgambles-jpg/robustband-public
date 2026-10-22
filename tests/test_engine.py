# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""引擎核心：族构造、打分表、rank/score 主张、δ 带与判决。"""
import robustband as rb
import pytest
from robustband.core import Perturbation


def test_family_size_and_uniqueness():
    fam = rb.build_family()
    assert len(fam) == 80  # 5 parse × 4 metric × 4 agg
    assert len({str(h) for h in fam}) == 80


def test_perturbation_str():
    assert str(Perturbation("last_num", "exact_match", "micro")) == "last_num|exact_match|micro"


def test_axes_cardinality():
    assert len(rb.PARSE) == 5
    assert len(rb.METRIC) == 4
    assert len(rb.AGG) == 4


def test_rank_margin_single_config_robust(flip_preds):
    fam = rb.build_family(parses=["last_num"], metrics=["exact_match"], aggs=["micro"])
    b = rb.evaluate(flip_preds, fam, rb.RankClaim("cot", "plain"))
    assert b.n_configs == 1
    assert b.margins["last_num|exact_match|micro"] == 1.0
    assert b.delta == (1.0, 1.0)
    assert b.verdict == "ROBUST"
    assert b.break_set == []


def test_flip_is_unidentifiable(flip_preds):
    fam = rb.build_family(parses=["first_num", "last_num"],
                          metrics=["exact_match"], aggs=["micro"])
    b = rb.evaluate(flip_preds, fam, rb.RankClaim("cot", "plain"))
    assert b.n_configs == 2
    assert b.delta == (-1.0, 1.0)
    assert b.verdict == "UNIDENTIFIABLE"
    assert b.break_set == ["first_num|exact_match|micro"]
    assert abs(b.stability_fraction - 0.5) < 1e-12


def test_rank_refuted(flip_preds):
    # 断言 cot>plain 在 first_num 下被反驳（margin 全负）
    fam = rb.build_family(parses=["first_num"], metrics=["exact_match"], aggs=["micro"])
    b = rb.evaluate(flip_preds, fam, rb.RankClaim("cot", "plain"))
    assert b.verdict == "REFUTED"
    assert b.delta == (-1.0, -1.0)


def test_all_ties_refute_strict_rank():
    preds = {"a": {"items": [("0", "42", {})]},
             "b": {"items": [("0", "42", {})]}}
    fam = rb.build_family(parses=["strict_exact"], metrics=["exact_match"], aggs=["micro"])
    band = rb.evaluate(preds, fam, rb.RankClaim("a", "b"))
    assert band.delta == (0.0, 0.0)
    assert band.verdict == "REFUTED"
    assert rb.certificate.impossibility_certificate(band) is None


def test_tie_and_win_does_not_claim_strict_reversal():
    preds = {"a": {"items": [("42 no wait 7", "42", {})]},
             "b": {"items": [("7", "42", {})]}}
    fam = rb.build_family(parses=["strict_exact", "first_num"],
                          metrics=["exact_match"], aggs=["micro"])
    band = rb.evaluate(preds, fam, rb.RankClaim("a", "b"))
    cert = rb.certificate.impossibility_certificate(band)
    assert band.delta == (0.0, 1.0)
    assert band.verdict == "UNIDENTIFIABLE"
    assert cert["strict_sign_flip"] is False


def test_reject_unsupported_tolerance_and_empty_family(flip_preds):
    claim = rb.RankClaim("cot", "plain")
    fam = rb.build_family(parses=["last_num"], metrics=["exact_match"], aggs=["micro"])
    with pytest.raises(ValueError, match="tol_eps"):
        rb.evaluate(flip_preds, fam, claim, tol_eps=0.1)
    assert rb.build_family(parses=[]) == []
    with pytest.raises(ValueError, match="family"):
        rb.evaluate(flip_preds, [], claim)


def test_score_claim_greater_and_less(flip_preds):
    fam = rb.build_family(parses=["last_num"], metrics=["exact_match"], aggs=["micro"])
    # cot 分数=1 > 0.5 → 成立
    assert rb.evaluate(flip_preds, fam, rb.ScoreClaim("cot", 0.5)).verdict == "ROBUST"
    # plain 分数=0 < 0.5 → 不成立（REFUTED）
    assert rb.evaluate(flip_preds, fam, rb.ScoreClaim("plain", 0.5)).verdict == "REFUTED"
    # 反向 ScoreClaim（< 阈值）在 plain 上成立
    b = rb.evaluate(flip_preds, fam, rb.ScoreClaim("plain", 0.5, greater=False))
    assert b.verdict == "ROBUST"


def test_micro_score_value():
    preds = {"m": {"items": [
        ("1", "1", {"class": "a", "len_bucket": 0}),
        ("x", "9", {"class": "b", "len_bucket": 1}),
    ]}}
    fam = rb.build_family(parses=["last_num"], metrics=["exact_match"], aggs=["micro"])
    b = rb.evaluate(preds, fam, rb.ScoreClaim("m", 0.0))
    assert abs(b.margins["last_num|exact_match|micro"] - 0.5) < 1e-12


def test_macro_class_vs_micro_differ():
    # a 类全对、b 类全错：micro=0.75，macro_class=(1+0)/2=0.5
    preds = {"m": {"items": [
        ("1", "1", {"class": "a", "len_bucket": 0}),
        ("2", "2", {"class": "a", "len_bucket": 0}),
        ("3", "3", {"class": "a", "len_bucket": 0}),
        ("x", "9", {"class": "b", "len_bucket": 1}),
    ]}}
    f_micro = rb.build_family(parses=["last_num"], metrics=["exact_match"], aggs=["micro"])
    f_macro = rb.build_family(parses=["last_num"], metrics=["exact_match"], aggs=["macro_class"])
    bm = rb.evaluate(preds, f_micro, rb.ScoreClaim("m", 0.0))
    bM = rb.evaluate(preds, f_macro, rb.ScoreClaim("m", 0.0))
    assert abs(bm.margins["last_num|exact_match|micro"] - 0.75) < 1e-12
    assert abs(bM.margins["last_num|exact_match|macro_class"] - 0.5) < 1e-12


def test_band_to_dict(flip_preds):
    fam = rb.build_family(parses=["first_num", "last_num"],
                          metrics=["exact_match"], aggs=["micro"])
    d = rb.evaluate(flip_preds, fam, rb.RankClaim("cot", "plain")).to_dict()
    assert d["n_break"] == 1
    assert d["n_configs"] == 2
    assert d["verdict"] == "UNIDENTIFIABLE"
    assert d["delta"] == (-1.0, 1.0)

def test_cached_scoring_matches_a_per_protocol_reference(flip_preds):
    """The cached prepare step must not change any aggregated score or margin."""
    family = rb.build_family(parses=["first_num", "last_num"],
                             metrics=["exact_match", "contains"],
                             aggs=["micro", "macro_class"])
    claim = rb.RankClaim("cot", "plain")
    band = rb.evaluate(flip_preds, family, claim)
    for h in family:
        expected = {}
        for model, blob in flip_preds.items():
            corrects, metas = [], []
            for raw, gold, meta in blob["items"]:
                corrects.append(rb.METRIC[h.metric](rb.PARSE[h.parse](raw), gold, meta))
                metas.append(meta or {})
            expected[model] = rb.AGG[h.agg](corrects, metas)
        assert rb.score_table(flip_preds, h) == expected
        assert band.margins[str(h)] == claim.margin(expected)
