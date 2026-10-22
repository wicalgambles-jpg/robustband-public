# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""E 负模块：不可行性证书 / 最小反例 / 统一出口 emit。"""
import robustband as rb


def test_impossibility_certificate_present(flip_preds):
    fam = rb.build_family()
    claim = rb.RankClaim("cot", "plain")
    b = rb.evaluate(flip_preds, fam, claim)
    cert = rb.certificate.impossibility_certificate(b)
    assert cert is not None
    assert cert["type"] == "impossibility_certificate"
    assert cert["witness_positive"]["config"]
    assert cert["witness_negative"]["config"]
    assert cert["witness_positive"]["margin"] > 0
    assert cert["witness_negative"]["margin"] < 0


def test_minimal_counterexample(flip_preds):
    fam = rb.build_family(parses=["first_num", "last_num"],
                          metrics=["exact_match"], aggs=["micro"])
    claim = rb.RankClaim("cot", "plain")
    b = rb.evaluate(flip_preds, fam, claim)
    mce = rb.certificate.minimal_counterexample(flip_preds, fam, claim, b)
    assert mce is not None
    assert mce["type"] == "minimal_counterexample"
    assert mce["config"] == "first_num|exact_match|micro"
    assert mce["margin"] == -1.0
    assert mce["repro"]["parse"] == "first_num"
    assert "cot" in mce["table_under_config"]


def test_emit_prefers_impossibility(flip_preds):
    fam = rb.build_family()
    claim = rb.RankClaim("cot", "plain")
    b = rb.evaluate(flip_preds, fam, claim)
    out = rb.certificate.emit(flip_preds, fam, claim, b)
    assert out["type"] == "impossibility_certificate"


def test_no_certificate_when_robust(flip_preds):
    fam = rb.build_family(parses=["last_num"], metrics=["exact_match"], aggs=["micro"])
    claim = rb.RankClaim("cot", "plain")
    b = rb.evaluate(flip_preds, fam, claim)
    assert b.break_set == []
    assert rb.certificate.minimal_counterexample(flip_preds, fam, claim, b) is None
    assert rb.certificate.impossibility_certificate(b) is None
    # 稳健时 emit 也应返回 None（既无不可行证书、也无反例）
    assert rb.certificate.emit(flip_preds, fam, claim, b) is None
