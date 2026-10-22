# SPDX-License-Identifier: MIT
"""Fragility-resource prototype: loaders, exact bands, gates, determinism and rendering."""
import importlib.util
import json
from fractions import Fraction
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("resource_grid", ROOT / "experiments" / "resource_grid.py")
resource = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resource)


def write_evalscope(path, rows):
    lines = []
    for row in rows:
        lines.append(json.dumps({"index": 0, "target": row.get("target", ""),
                                 "messages": [{"role": "user", "content": "q"},
                                              {"role": "assistant", "content": row["output"]}],
                                 "sample_score": {"sample_id": row["sample_id"],
                                                  "sample_metadata": row.get("meta", {}),
                                                  "score": {"value": row.get("scores", {})}}}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_evalscope_and_demo_loaders_normalise_records(tmp_path):
    path = tmp_path / "review.jsonl"
    write_evalscope(path, [{"sample_id": 3, "target": "42", "output": "the answer is 42",
                            "meta": {"class": "x"}, "scores": {"prompt_level_strict": 1.0}}])
    records = resource._evalscope_records(path)
    assert records == [{"sample_id": "3", "raw": "the answer is 42", "gold": "42",
                        "meta": {"class": "x"}, "upstream": {"prompt_level_strict": 1.0}}]
    demo = tmp_path / "demo.jsonl"
    demo.write_text(json.dumps({"raw": "r", "gold": "1", "meta": {"len_bucket": 2}}) + "\n", encoding="utf-8")
    assert resource._demo_records(demo) == [{"sample_id": "0", "raw": "r", "gold": "1",
                                             "meta": {"len_bucket": 2}, "upstream": {}}]


def test_evalscope_loader_requires_a_sample_id(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"messages": [], "sample_score": {}}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sample_id"):
        resource._evalscope_records(path)


def test_band_reports_width_and_extreme_protocols():
    band = resource._band({"a": Fraction(1, 2), "b": Fraction(1, 10), "c": Fraction(9, 10)})
    assert band == {"lo": "1/10", "hi": "9/10", "width": "4/5", "min_protocol": "b",
                    "max_protocol": "c", "width_float": 0.8}


def test_recorded_scores_use_exact_mean_and_median():
    records = [{"upstream": {"m": "1.0"}}, {"upstream": {"m": "0.5"}}, {"upstream": {"m": "0.5"}}]
    scores = resource._scores_recorded(records, ["m"])
    assert scores["m|mean"] == Fraction(2, 3) and scores["m|median"] == Fraction(1, 2)
    with pytest.raises(ValueError, match="Missing upstream score"):
        resource._scores_recorded([{"upstream": {}}], ["m"])


def test_ranking_ties_share_the_best_rank():
    pairs = {"a": {"p": Fraction(1)}, "b": {"p": Fraction(1)}, "c": {"p": Fraction(0)}}
    rows = resource._ranking(pairs, ["a", "b", "c"])
    assert rows[0]["ranks"] == {"a": 1, "b": 1, "c": 3}
    assert rows[0]["leaders"] == ["a", "b"]


def test_raw_scores_show_the_hand_checkable_flip():
    records = [{"raw": "7 then 42", "gold": "42", "meta": {}},
               {"raw": "7 then 42", "gold": "42", "meta": {}}]
    family = [("first_num", "exact_match", "micro"), ("last_num", "exact_match", "micro")]
    scores = resource._scores_raw(records, family)
    assert scores["first_num|exact_match|micro"] == 0
    assert scores["last_num|exact_match|micro"] == 1


def test_analyze_records_gates_pairs_and_is_deterministic():
    local = ROOT / "experiments" / "resource_test_manifest.json"
    local.write_text(json.dumps({"schema": "robustband.resource_sources/v1", "benchmarks": [
        {"id": "toy", "kind": "raw_output", "files": {
            "a": "examples/data/evalscope/qwen-plus/gsm8k_main.jsonl",
            "b": "examples/data/evalscope/qwen3-max/gsm8k_main.jsonl"}}]}), encoding="utf-8")
    try:
        first = resource.analyze(local)
        second = resource.analyze(local)
    finally:
        local.unlink()
    assert first == second
    assert first["summary"]["n_models"] == 2 and first["summary"]["n_benchmarks"] == 1
    assert first["gates"]["R-B1a_models"] == {"required": 8, "actual": 2, "pass": False}
    assert first["gates"]["R-B5_decision_change"]["pass"] is None
    assert first["benchmarks"][0]["common_items"] == 10
    assert first["benchmarks"][0]["pairs"][0]["common_items"] == 10
    assert first["grid_sha256"]


def test_render_escapes_and_shows_the_gates():
    newest = max((ROOT / "results").glob("resource_grid_*.json"))
    result = json.loads(newest.read_text(encoding="utf-8"))
    html = resource.render(result)
    assert "预注册门" in html and "R-B1a_models" in html and "FAIL" in html
    assert "<script>" not in html


def test_unknown_manifest_schema_and_kind_are_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "other", "benchmarks": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        resource.load_sources(bad)
    bad.write_text(json.dumps({"schema": "robustband.resource_sources/v1", "benchmarks": [
        {"id": "x", "kind": "unknown", "files": {}}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="kind"):
        resource.load_sources(bad)


def test_full_grid_is_invariant_to_checkout_newlines_and_detects_changed_content(tmp_path, monkeypatch):
    """Provenance and the complete grid hash use the same normalized bytes."""
    monkeypatch.setattr(resource, 'ROOT', tmp_path)
    rows = [dict(sample_id='一', raw='7 then 42', gold='42', meta={'class':'x','len_bucket':'s'})]
    data = (json.dumps(rows[0], ensure_ascii=False)+'\n').encode('utf-8')
    sources = {'schema':'robustband.resource_sources/v1','benchmarks':[
        {'id':'toy','kind':'demo_raw','files':{'a':'a.jsonl','b':'b.jsonl'}}]}
    manifest = tmp_path/'manifest.json'
    manifest_lf = (json.dumps(sources, indent=2)+'\n').encode('utf-8')
    manifest.write_bytes(manifest_lf)
    for filename in ('a.jsonl','b.jsonl'): (tmp_path/filename).write_bytes(data)
    first = resource.analyze(manifest)
    assert first['schema']=='robustband.resource_grid/v2'
    assert first['files']['a.jsonl']['bytes_lf']==len(data)
    assert 'bytes' not in first['files']['a.jsonl']
    for filename in ('a.jsonl','b.jsonl'):
        (tmp_path/filename).write_bytes(data.replace(b'\n',b'\r\n'))
    manifest.write_bytes(manifest_lf.replace(b'\n',b'\r\n'))
    assert resource.analyze(manifest)==first
    changed = data.replace(b'7 then 42',b'7 then 41')
    assert len(changed)==len(data)
    (tmp_path/'a.jsonl').write_bytes(changed)
    actual = resource.analyze(manifest)
    assert actual['files']['a.jsonl']['bytes_lf']==first['files']['a.jsonl']['bytes_lf']
    assert actual['files']['a.jsonl']['sha256_lf']!=first['files']['a.jsonl']['sha256_lf']
    assert actual['grid_sha256']!=first['grid_sha256']
