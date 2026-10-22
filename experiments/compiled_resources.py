# SPDX-License-Identifier: MIT
"""Matched raw/cached runtime and Python allocation measurements; no inference."""
from hashlib import sha256
import json
from pathlib import Path
import platform
import random
import statistics
import sys
from time import perf_counter
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import robustband as rb
from robustband.compiled import CompiledScores
from examples.review_budget import load_problem
from experiments.compiled_benchmark import run


def main():
    _, preds = load_problem()
    family, claim = rb.build_family(), rb.RankClaim("cot", "plain")
    rng = random.Random(20261012)
    indices = [[rng.randrange(24) for _ in range(24)] for _ in range(100)]
    seconds = {"raw": [], "cached_including_compile": []}
    outputs, peaks = {}, {}
    for repetition in range(3):
        for method in (("raw", "cached_including_compile") if repetition % 2 == 0 else
                       ("cached_including_compile", "raw")):
            start = perf_counter()
            compiled = CompiledScores(preds, family) if method != "raw" else None
            result = run(preds, family, claim, indices, compiled)
            seconds[method].append(perf_counter() - start)
            outputs[method] = result
    assert outputs["raw"] == outputs["cached_including_compile"]
    for method in seconds:
        # Inputs/indices preexist. Snapshot construction is included in cached peak.
        compiled = None
        tracemalloc.start()
        if method != "raw":
            compiled = CompiledScores(preds, family)
        result = run(preds, family, claim, indices, compiled)
        retained, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert result == outputs[method]
        peaks[method] = {"peak_bytes": peak, "retained_bytes_at_end": retained}
    medians = {k: statistics.median(v) for k, v in seconds.items()}
    report = {"schema": "robustband.compiled_resources/v1", "version": rb.__version__,
        "date": "2026-10-12", "python": platform.python_version(), "platform": platform.platform(),
        "n_pairs": 24, "n_configs": 80, "resamples": 100, "seed": 20261012,
        "timing": "Median of three alternating-order untraced runs; snapshot construction included",
        "timing_samples_seconds": seconds, "median_seconds": medians,
        "observed_speedup": medians["raw"] / medians["cached_including_compile"],
        "python_allocations": peaks,
        "memory_scope": "Separate traced 100-resample pass; excludes preexisting inputs/indices, includes cached snapshot; Python allocations, not RSS or total system memory",
        "raw_and_cached_outputs": outputs, "every_band_field_identical": True,
        "source_sha256_lf": {p: sha256((ROOT / p).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for p in ["experiments/compiled_resources.py", "experiments/compiled_benchmark.py",
                      "examples/review_budget.py", "demo/data_real/cot.jsonl", "demo/data_real/plain.jsonl"]
            + [str(p.relative_to(ROOT)).replace("\\", "/") for p in sorted((ROOT / "robustband").glob("*.py"))]},
        "limits": ["Single Windows/Python environment, small frozen sample", "No timing assertion or universal speed claim", "Caching is established engineering, not a novel mathematical method"]}
    (ROOT / "results/compiled_resources_0.4.0.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"median_seconds": medians, "observed_speedup": report["observed_speedup"],
                      "python_allocations": peaks}))


if __name__ == "__main__":
    main()
