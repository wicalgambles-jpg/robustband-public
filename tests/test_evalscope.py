# SPDX-License-Identifier: MIT
"""Import gates prevent silently pairing unrelated outputs or trusting scores."""
from copy import deepcopy
from fractions import Fraction
import json

import pytest
import robustband as rb
from robustband.evalscope import EvalScopeAdapter


def row(identity=0, prediction="2", score=1):
    return {"target": "2", "messages": [{"role": "user", "content": "one plus one"},
            {"role": "assistant", "content": prediction}], "sample_score": {
            "sample_id": identity, "sample_metadata": {"key": 100},
            "score": {"prediction": prediction, "value": {"acc": score}}}}


def write(tmp_path, rows, name="a"):
    path = tmp_path / (name + ".jsonl")
    path.write_text("\n" + "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def test_alignment_raw_and_exact_logged_scores(tmp_path):
    a = write(tmp_path, [row("x", score=0.1), row(0)])
    b = write(tmp_path, [row(0, "3", 0), row("x", "3", 0)], "b")
    adapter = EvalScopeAdapter({"A": a, "B": b})
    records = adapter.records()
    assert [r["sample_id"] for r in records["B"]] == [0, "x"]
    assert records["A"][1]["scores"]["acc"] == Fraction(1, 10)
    preds = adapter.load()
    assert preds["B"]["items"][0] == ("3", "2", {"sample_id": 0, "source_metadata": {"key": 100}})
    family = rb.build_family(parses=["last_num"], metrics=["exact_match"], aggs=["micro"])
    assert rb.evaluate(preds, family, rb.RankClaim("A", "B")).delta == (1, 1)


@pytest.mark.parametrize("files", [{}, {"": "a"}, {2: "a"}])
def test_model_names(files):
    with pytest.raises(ValueError):
        EvalScopeAdapter(files)


@pytest.mark.parametrize("bad", [None, {}, {"sample_score": None}])
def test_incomplete_records(tmp_path, bad):
    with pytest.raises(ValueError, match="incomplete"):
        EvalScopeAdapter({"A": write(tmp_path, [bad])}).load()


@pytest.mark.parametrize("change", [
    lambda r: r["sample_score"].update(sample_id=True),
    lambda r: r["sample_score"].update(sample_id=""),
    lambda r: r.update(target=2),
    lambda r: r["sample_score"].update(sample_metadata=[]),
    lambda r: r["sample_score"]["score"].update(prediction=2),
    lambda r: r.update(messages=[]),
    lambda r: r["messages"][0].update(content=2),
    lambda r: r["messages"][-1].update(content="different"),
    lambda r: r["sample_score"]["score"].update(value={}),
    lambda r: r["sample_score"]["score"].update(value=[]),
    lambda r: r["sample_score"]["score"].update(value={"": 1}),
    lambda r: r["sample_score"]["score"].update(value={"acc": True}),
    lambda r: r["sample_score"]["score"].update(value={"acc": "1"}),
    lambda r: r["sample_score"]["score"].update(value={"acc": 1.1}),
    lambda r: r["sample_score"]["score"].update(value={"acc": -1}),
])
def test_record_schema(tmp_path, change):
    bad = row()
    change(bad)
    with pytest.raises(ValueError):
        EvalScopeAdapter({"A": write(tmp_path, [bad])}).records()


def test_duplicate_empty_and_invalid_json(tmp_path):
    for rows, match in [([row(), row()], "duplicate"), ([], "empty")]:
        with pytest.raises(ValueError, match=match):
            EvalScopeAdapter({"A": write(tmp_path, rows)}).records()
    path = write(tmp_path, [])
    for content in ["{broken", json.dumps(row(score=float("nan")))]:
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError):
            EvalScopeAdapter({"A": path}).records()


@pytest.mark.parametrize("change,match", [
    (lambda r: r["sample_score"].update(sample_id=1), "sample-ID"),
    (lambda r: r.update(target="3"), "paired"),
    (lambda r: r["messages"][0].update(content="other question"), "paired"),
    (lambda r: r["sample_score"]["sample_metadata"].update(key=101), "paired"),
])
def test_pairing_drift(tmp_path, change, match):
    bad = deepcopy(row())
    change(bad)
    with pytest.raises(ValueError, match=match):
        EvalScopeAdapter({"A": write(tmp_path, [row()]), "B": write(tmp_path, [bad], "b")}).records()
