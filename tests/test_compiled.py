# SPDX-License-Identifier: MIT
"""Cross-path equivalence and input-isolation checks for compiled scoring."""
from copy import deepcopy
import random

import pytest
import robustband as rb
from robustband.compiled import CompiledScores


def sample():
    a = [("1 but 2", "2", {"class": "a", "len_bucket": 0}),
         ("2 but 1", "2", {"class": "a", "len_bucket": 1}),
         ("3", "3", {"class": "b", "len_bucket": 1})]
    b = [("2 but 1", "2", {"class": "a", "len_bucket": 0}),
         ("1 but 2", "2", {"class": "a", "len_bucket": 1}),
         ("x", "3", {"class": "b", "len_bucket": 1})]
    return {"a": {"items": a}, "b": {"items": b}}


def test_all_band_fields_match_full_and_paired_resamples():
    preds, family = sample(), rb.build_family()
    compiled = CompiledScores(preds, family)
    rng = random.Random(42)
    claims = [rb.RankClaim("a", "b"), rb.ScoreClaim("a", 0.3), rb.ScoreClaim("b", 0.5, greater=False)]
    for claim in claims:
        assert compiled.evaluate(claim).to_dict() == rb.evaluate(preds, family, claim).to_dict()
        for idx in [[], [0, 0, 0], *[[rng.randrange(3) for _ in range(3)] for _ in range(20)]]:
            resample = {k: {"items": [v["items"][i] for i in idx]} for k, v in preds.items()}
            assert compiled.evaluate(claim, idx).to_dict() == rb.evaluate(resample, family, claim).to_dict()


def test_snapshot_isolated_from_later_input_and_registry_changes(monkeypatch):
    preds = sample()
    original = deepcopy(preds)
    family = rb.build_family(parses=["last_num"], metrics=["exact_match"], aggs=["macro_class"])
    compiled = CompiledScores(preds, family)
    expected = rb.evaluate(original, family, rb.RankClaim("a", "b")).to_dict()
    preds["a"]["items"][0][2]["class"] = "edited"
    preds["a"]["items"][0] = ("wrong", "2", {})
    monkeypatch.setitem(rb.AGG, "macro_class", lambda corrects, metas: 99)
    assert compiled.evaluate(rb.RankClaim("a", "b")).to_dict() == expected


def test_parse_work_does_not_scale_with_aggregators_or_bootstraps(monkeypatch):
    calls = []
    parse = rb.PARSE["last_num"]
    def counted(raw):
        calls.append(raw)
        return parse(raw)
    monkeypatch.setitem(rb.PARSE, "last_num", counted)
    family = rb.build_family(parses=["last_num"], metrics=["exact_match", "contains"])
    compiled = CompiledScores(sample(), family)
    assert len(calls) == 6
    for _ in range(10):
        compiled.evaluate(rb.RankClaim("a", "b"), [2, 1, 2])
    assert len(calls) == 6


def test_reject_empty_family_unpaired_or_invalid_indices():
    with pytest.raises(ValueError, match="family"):
        CompiledScores(sample(), [])
    family = rb.build_family()
    compiled = CompiledScores(sample(), family)
    for idx in ([3], [-1], [0.5], [True]):
        with pytest.raises(ValueError, match="indices"):
            compiled.evaluate(rb.RankClaim("a", "b"), idx)
    preds = sample()
    preds["b"]["items"].pop()
    compiled = CompiledScores(preds, family)
    with pytest.raises(ValueError, match="equal"):
        compiled.evaluate(rb.RankClaim("a", "b"), [0])
    preds = sample()
    preds["b"]["items"][0][2]["class"] = "different"
    compiled = CompiledScores(preds, family)
    with pytest.raises(ValueError, match="aligned"):
        compiled.evaluate(rb.RankClaim("a", "b"), [0])
