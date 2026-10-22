# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""适配器：内存 / JSONL，及与引擎的端到端回环。"""
import json

import robustband as rb


def test_inmemory_adapter_roundtrip(flip_preds):
    a = rb.InMemoryAdapter(flip_preds, name="x")
    assert a.load() is flip_preds


def test_jsonl_adapter_roundtrip(tmp_path, flip_items):
    cot, plain = flip_items
    for model, items in [("cot", cot), ("plain", plain)]:
        p = tmp_path / f"{model}.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for raw, gold, meta in items:
                f.write(json.dumps({"raw": raw, "gold": gold, "meta": meta}) + "\n")

    adapter = rb.JSONLAdapter(tmp_path, name="t")
    preds = adapter.load()
    assert set(preds) == {"cot", "plain"}
    assert preds["cot"]["items"][0][0] == cot[0][0]

    fam = rb.build_family(parses=["first_num", "last_num"],
                          metrics=["exact_match"], aggs=["micro"])
    b = rb.evaluate(preds, fam, rb.RankClaim("cot", "plain"))
    assert b.delta == (-1.0, 1.0)
    assert b.verdict == "UNIDENTIFIABLE"


def test_jsonl_adapter_model_filter(tmp_path, flip_items):
    cot, plain = flip_items
    for model, items in [("cot", cot), ("plain", plain)]:
        p = tmp_path / f"{model}.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for raw, gold, meta in items:
                f.write(json.dumps({"raw": raw, "gold": gold, "meta": meta}) + "\n")
    adapter = rb.JSONLAdapter(tmp_path, name="t", models=["cot"])
    assert set(adapter.load()) == {"cot"}
