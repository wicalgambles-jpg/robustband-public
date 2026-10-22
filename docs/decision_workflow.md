# Check whether a candidate meets adoption criteria

Use **Adoption check** in the local app when a model or software update must
improve one objective while protecting others. Declare a primary target, optional
guardrails, an exact threshold, a boundary rule and justified scoring protocols.
Each target keeps its own units, evidence and result.

## Browser workflow

1. Start your edition with its Windows launcher or `python -m robustband ui`.
   Click **Adoption check** at the top. Run the synthetic example first.
2. Choose your data kind and import paired results. For numeric files, either
   use the standard paired format or map your own sample ID, A/B score columns,
   metric names, original units, directions and optional group column.
3. Check the available targets. Select exactly one primary target, then any
   guardrails. State why the rules are appropriate before calculating.
4. Enter thresholds in the **oriented margin unit**. Save the criteria file for
   reuse or version control, then run the check. A file hash records content;
   saving does not establish preregistration.
5. Read each target's range, endpoint rules and unmet conditions. Save HTML for
   reading and JSON for exact replay. Changing data or criteria clears the old
   result.

The professional profile uses the original text domain. The generalized profile
supports text, segmentation and numeric decision targets. Trusted custom adapters
continue to use the existing single-target workflow; the initial decision-plan
schema covers these three built-in domains.

## Thresholds and boundary rules

Positive oriented margins mean A is better: A−B when higher is better, B−A when
lower is better. Thresholds apply to aggregated differences, not to every sample.

| Measurement | Input unit | Threshold unit |
| --- | --- | --- |
| Recorded accuracy 80 vs 79 | `percent` | Percentage points (`pp`): difference 1 |
| Recorded accuracy 0.80 vs 0.79 | `fraction` | Recorded fraction: difference 0.01 |
| Latency | `ms`, direction `lower` | Milliseconds saved |
| Segmentation IoU from counts | Integer counts | Percentage points (`pp`) |
| Text correctness | Raw paired answers | Score difference, on the 0–1 scale |

`gt` means strictly greater than the threshold; equality fails. `ge` means at
least the threshold; equality passes. For example, `ge -0.5` on a percent metric
allows a decline of at most 0.5 percentage points. Numeric plans bind the expected
metric, input unit and direction; changing any of them requires an explicit plan
revision. No automatic unit conversion is performed.

## Results

Each target is `PASS` if every selected rule meets its condition, `FAIL` if no
selected rule meets it, and `REVIEW` otherwise. The overall check is:

| Overall result | Meaning |
| --- | --- |
| PASS | Every target passes under every rule selected for that target |
| FAIL | At least one target fails under every rule selected for it |
| REVIEW | Remaining cases, where conditions depend on scoring choices |

A passing primary target with a failing guardrail is an **objective tradeoff**.
Rule-dependent outcomes within one target are **protocol sensitivity**. Different
metrics are never averaged into a combined score. The check evaluates per-target
requirements; it does not assert the existence of a joint passing configuration
when targets have mixed outcomes.

These ranges describe supplied records and declared rules. Sampling uncertainty,
dependent frames, measurement validity and deployment performance require their
own evidence. Protocol counts are not independent votes or confidence levels.

## Numeric inputs

Standard paired long format can contain several metrics:

```csv
sample_id,score_a,score_b,metric,unit,direction
seed-1,82,80,accuracy,percent,higher
seed-1,7,8,rare_class,percent,higher
seed-2,84,80,accuracy,percent,higher
seed-2,8,9,rare_class,percent,higher
```

IDs must be unique **within each metric**. All selected metrics must have identical
sample ID sets and group labels; record order may differ. Missing seeds are
rejected, with no implicit inner join. Unselected metrics are listed in the
report. Mixed units or directions within a metric are rejected.

For wide files, use explicit column mapping. The shipped synthetic example uses
`seed,overall_a,overall_b,human_a,human_b`. Mapping preserves decimal strings and
never guesses whether values represent percentages, fractions or confusion counts.
The 5,000-record limit also applies after expansion into metric records.

## Command line and automated gates

```bash
python -m robustband decision-template audit-demo/decision-input
python -m robustband decision audit-demo/decision-input/paired.csv --plan audit-demo/decision-input/plan.json --mapping audit-demo/decision-input/mapping.json --output audit-results/decision --require-pass
python -m robustband verify audit-results/decision/report.json
```

The synthetic example intentionally has a passing benefit and a failing
guardrail. With `--require-pass`, exit codes are **0: PASS**, **1: FAIL or REVIEW**,
**2: invalid input or execution error**. Reports are written for valid FAIL/REVIEW
checks as well. Without `--require-pass`, a completed check exits 0.

Omit `--mapping` for standard long-format numeric data, text or confusion counts.
Use `--format jsonl` for JSONL. Plans contain `schema`, `domain`, `name`,
`rationale`, and `targets`. A target contains `id`, `label`, `role`, `family`,
`threshold` (decimal string), `operator`, and `reason`; numeric targets additionally
declare `metric`, `unit`, and `direction`. Segmentation `family.classes` selects
each target's class set independently. See the generated plan for a complete
numeric example and [domain formats](domains.md) for domain-specific families.

Adapt [the CI example](../examples/decision_gate.yml) to your repository. Keep
criteria under version control and record changes separately from measured
results. A policy revision changes the decision specification; it does not improve
the measured model.

Replay recomputes the original input mapping, every nested target audit, exact
thresholds, final decisions, and source bindings. **The JSON includes the complete
original file, including unused columns and metrics. Review it before sharing.**
