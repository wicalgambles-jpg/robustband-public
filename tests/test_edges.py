# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""边界臂覆盖：空输入退化、缺 meta 键的宏聚合、空 margins 证书、空族拒绝、
适配器基类与空行跳过。

原则：只覆盖**库代码未改**的边界分支；断言使用可手算的精确值，
不引入随机与外部数据。
"""
import json
from fractions import Fraction

import pytest

import robustband as rb


# ---- parsers：空行退化 / \boxed{} 抽取与回退 ----

def test_last_line_num_blank_only_returns_empty():
    assert rb.parsers.p_last_line_num("   \n\n  ") == ""
    assert rb.parsers.p_last_line_num("") == ""


def test_boxed_extracts_inner_then_falls_back_to_last_num():
    assert rb.parsers.p_boxed(r"so the answer is \boxed{42} indeed") == "42"
    assert rb.parsers.p_boxed("no box here: 7") == "7"


# ---- metrics：数值等价（非字符串相等）/ 单侧为空 ----

def test_exact_match_accepts_numerically_equal_strings():
    assert rb.metrics.m_exact("42.0", "42") == 1
    assert rb.metrics.m_exact("1,000", "1000") == 1
    assert rb.metrics.m_exact("42", "43") == 0


def test_f1_token_with_empty_side_is_zero():
    assert rb.metrics.m_f1_token("", "42") == 0
    assert rb.metrics.m_f1_token("42", "") == 0


# ---- aggregate：宏聚合缺 meta 键时退化到全样本 ----

def test_macro_aggregation_without_meta_key_falls_back_to_micro():
    corrects, metas = [1, 0], [{}, {}]
    assert rb.aggregate.a_macro_class(corrects, metas) == 0.5
    assert rb.aggregate.a_macro_len(corrects, metas) == 0.5
    assert rb.aggregate.a_macro_class(corrects, metas) == rb.aggregate.a_micro(corrects, metas)


# ---- certificate：margins 为空时见证为 None ----

def test_impossibility_certificate_without_margins_has_no_witness():
    band = rb.Band(
        stability_fraction=0.0,
        break_set=[],
        delta=(0.0, 1.0),
        verdict="UNIDENTIFIABLE",
        n_configs=1,
    )  # margins 取默认空 dict
    cert = rb.certificate.impossibility_certificate(band)
    assert cert is not None
    assert cert["strict_sign_flip"] is False
    assert cert["witness_positive"] is None
    assert cert["witness_negative"] is None


# ---- rational：空样本 / 缺 meta 键 / 空配置族拒绝 ----

def test_score_frac_empty_and_macro_missing_key():
    assert rb.rational.score_frac([], [], "micro") == Fraction(0)
    assert rb.rational.score_frac([1, 0], [{}, {}], "macro_class") == Fraction(1, 2)


def test_rational_band_rejects_empty_family():
    with pytest.raises(ValueError):
        rb.rational.rational_band([], [], family=[])


# ---- adapter：基类未实现 / 空行跳过 ----

def test_base_adapter_load_is_not_implemented():
    with pytest.raises(NotImplementedError):
        rb.BenchmarkAdapter().load()


def test_jsonl_adapter_skips_blank_lines(tmp_path):
    p = tmp_path / "cot.jsonl"
    p.write_text(
        json.dumps({"raw": "the answer is 7 but really 42", "gold": "42", "meta": {}}) + "\n"
        + "\n"
        + "   \n"
        + json.dumps({"raw": "42 no wait 7", "gold": "42", "meta": {}}) + "\n",
        encoding="utf-8",
    )
    preds = rb.JSONLAdapter(tmp_path).load()
    assert set(preds) == {"cot"}
    assert len(preds["cot"]["items"]) == 2
