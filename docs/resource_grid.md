# Fragility resource (pipeline validation)

`experiments/resource_grid.py` is the prototype of the **resource track**: it scores an
archive of per-item model outputs under a declared protocol family and records how far a
conclusion can move when only the scoring rules change.

It is deliberately separate from the product surface. The product audits one comparison;
the resource records the whole grid so that others can reuse it.

## What it computes

| kind | per-item input | protocol axis | output |
|---|---|---|---|
| `raw_output` | raw model output + reference answer | parse × metric × aggregation (80) | exact per-model score band, pair bands, per-protocol leaders |
| `recorded_scores` | upstream per-item scores (for example instruction-following judges) | metric variant × aggregation | same, without re-running the upstream judge |

Every score is an exact `Fraction`; the JSON keeps the rational strings and the HTML report
shows readable values. `--verify` recomputes the whole grid from the manifest and fails on
any difference.

## Run

```bash
python -S experiments/resource_grid.py                       # writes results/resource_grid_<version>.{json,html}
python -S experiments/resource_grid.py --verify results/resource_grid_1.0.0.json
```

The manifest is `experiments/resource_sources.json`: each benchmark names its files, and
every file is hashed into the artifact so a later run cannot silently use different data.

## Current state (archive shipped with the repository)

| gate | requirement | measured | status |
|---|---|---|---|
| R-B1a | ≥ 8 models | 3 | **FAIL** |
| R-B1b | ≥ 4 benchmarks (full test sets) | 3 entries, two of them 10-item review samples | **FAIL** |
| R-B2 | ≥ 2 benchmarks with a model score width ≥ 0.10 | 3 of 3 | PASS |
| R-B3 | ≥ 1 model pair with a strict sign flip | 0 pairs | **FAIL** |
| R-B4 | recomputable from the recorded inputs | `--verify` passes | PASS |
| R-B5 | decision change | not evaluated (no paired decision task) | — |

**Why R-B3 fails is itself the finding.** The only paired archive has 10 items per
benchmark. On 10 items each item is 0.1 of the score, and one protocol choice can move a
score across the whole 0–1 range — for example `contains` accepts every output while
`exact_match` accepts none. The pair margins here are therefore `0` or `1/10`, near-tied and
never strictly reversed. The 1,319-item single-model archive shows a 0.4716 band, which is
the effect this resource is meant to measure; it simply has no second model to pair with.

Small archives coarsen widths and hide flips. A grid at publication scale needs full test
sets and several models per benchmark; a 10-item review sample is pipeline evidence, not a
population estimate.

## Reaching publication scale

1. **Models**: ≥ 8 per benchmark, including a small-model step (0.5B/1.5B) and at least one
   cross-family model. Outputs can come from GPU generation or from public per-item dumps;
   either way the manifest pins file hashes.
2. **Benchmarks**: ≥ 4 free-form generation benchmarks with full test sets. Reference
   answers are required for `raw_output`; instruction-following benchmarks enter through
   `recorded_scores` with their judge variants.
3. **Freeze**: fix the protocol family, the gates and the held-out benchmark/model before
   looking at the grid, and report negative results if a gate fails.

## Licensing and redistribution

The shipped archive comes from `modelscope/evalscope` (Apache-2.0, revision pinned in
`examples/data/evalscope/manifest.json`) and from frozen Qwen outputs already covered by
`THIRD_PARTY_NOTICES.md`. Publishing a larger resource requires the upstream licences to be
checked per benchmark and attributed in the release.
