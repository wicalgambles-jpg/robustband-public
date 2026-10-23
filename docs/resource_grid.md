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
python -S experiments/resource_grid.py --verify results/resource_grid_1.0.1.json
```

The manifest is `experiments/resource_sources.json`: each benchmark names its files, and
every file is hashed into the artifact so a later run cannot silently use different data.

### Checkout-independent provenance (1.0.1)

Schema `robustband.resource_grid/v2` records `sha256_lf` and `bytes_lf` from the
same UTF-8 file bytes after CRLF→LF normalization. The complete receipt and
`grid_sha256` are identical for LF and CRLF checkouts. Other byte changes remain
visible to the hash, including edits that preserve the file length.

```bash
python -S experiments/check_resource_portability.py
python submission/check_quality.py
```

The portability gate makes disposable LF and CRLF copies of every declared input
and compares both complete grids with the committed receipt. CI runs the full
release-quality gate on all nine OS/Python combinations.

The historical v1 receipts paired a normalized hash with a physical `bytes`
count. The 1.0.0 receipt was generated from CRLF data and fails strict replay on
an LF checkout. Those historical receipts and the 1.0.0 tag are preserved; use
the 1.0.1 receipt and v2 schema for portable replay.

## Current state (archive shipped with the repository)

| gate | requirement | measured | status |
|---|---|---|---|
| R-B1a | ≥ 8 models | 3 | **FAIL** |
| R-B1b | ≥ 4 benchmarks (full test sets) | 3 entries, two of them 10-item review samples | **FAIL** |
| R-B2 | ≥ 2 benchmarks with a model score width ≥ 0.10 | 3 of 3 | PASS |
| R-B3 | ≥ 1 model pair with a strict sign flip | 0 pairs | **FAIL** |
| R-B4 | recomputable from the recorded inputs | `--verify` passes | PASS |
| R-B5 | decision change | not evaluated (no paired decision task) | — |

The only paired archive has 10 items per benchmark. The observed pair margins
are `0` or `1/10`; no strict reversal was observed. The 1,319-item archive has a
single-model score width of 0.4716 and no second model to compare. These results
show that the pipeline runs on the recorded inputs. They do not establish that
small samples caused the absence of flips or that a larger archive will flip.

A larger study needs full test sets, multiple models and task-justified rules.
Large widths caused by permissive scorers do not establish useful decision
impact. A stable comparison is a valid outcome: retain negative results and
avoid adding rules until a desired reversal appears. The historical R-B3 target
describes a resource ambition, not a requirement for a valid user audit.

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
