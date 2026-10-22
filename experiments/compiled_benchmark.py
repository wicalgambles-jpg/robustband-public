# SPDX-License-Identifier: MIT
"""Compare every existing Band field on 2000 identical paired resamples."""
from hashlib import sha256
import json
from pathlib import Path
import platform
import random
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples"))
import robustband as rb
from robustband.compiled import CompiledScores
from review_budget import load_problem


def run(preds, family, claim, indices, compiled=None):
    digest = sha256()
    unidentifiable = flips = 0
    for idx in indices:
        if compiled is None:
            sample = {k: {"items": [v["items"][i] for i in idx]} for k, v in preds.items()}
            band = rb.evaluate(sample, family, claim)
        else:
            band = compiled.evaluate(claim, idx)
        digest.update(json.dumps(band.to_dict(), sort_keys=True, allow_nan=False).encode("utf-8"))
        unidentifiable += band.delta[0] <= 0 <= band.delta[1]
        flips += band.delta[0] < 0 < band.delta[1]
    return {"band_fields_sha256": digest.hexdigest(), "contains_zero_count": unidentifiable,
            "strict_flip_count": flips}


def main():
    protocol = json.loads((ROOT / "experiments/compiled_protocol.json").read_text(encoding="utf-8"))
    _, preds = load_problem()
    family, claim = rb.build_family(), rb.RankClaim("cot", "plain")
    rng = random.Random(protocol["seed"])
    indices = [[rng.randrange(24) for _ in range(24)] for _ in range(protocol["B"])]
    start = perf_counter()
    baseline = run(preds, family, claim, indices)
    baseline_seconds = perf_counter() - start
    print("baseline seconds=%.3f digest=%s" % (baseline_seconds, baseline["band_fields_sha256"]), flush=True)
    start = perf_counter()
    compiled = CompiledScores(preds, family)
    compile_seconds = perf_counter() - start
    accelerated = run(preds, family, claim, indices, compiled)
    total_compiled_seconds = perf_counter() - start
    if baseline != accelerated:
        raise AssertionError("compiled results disagree with the original scorer")
    result = {"schema": protocol["schema"], "date": protocol["date"], "B": protocol["B"],
              "seed": protocol["seed"], "python": platform.python_version(), "platform": platform.platform(),
              "baseline_seconds": baseline_seconds, "compiled_seconds_including_compile": total_compiled_seconds,
              "compile_seconds": compile_seconds, "observed_speedup": baseline_seconds / total_compiled_seconds,
              "baseline": baseline, "compiled": accelerated, "every_band_field_identical": True,
              "input_hashes": {name: sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                  for name in ("demo/data_real/cot.jsonl", "demo/data_real/plain.jsonl", "experiments/compiled_protocol.json")},
              "scope": "single local engineering measurement; caching is not a novel evaluation method"}
    (ROOT / "results/compiled_benchmark_2026-10-12.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("compiled seconds=%.3f speedup=%.2fx identical=True" %
          (total_compiled_seconds, result["observed_speedup"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
