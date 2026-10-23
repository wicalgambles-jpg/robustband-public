# Choose rules for a task

Start with the decision and the scoring specification. Record why each included
rule is plausible before looking at model names or rankings. The library's
80-rule default enumerates available implementations; the guided text example
starts with two rules. Neither selection establishes suitability for new data.

## Check three consequences before comparing

| Rule | Hand-checkable consequence | Selection question |
|---|---|---|
| `contains` | Reference `42`, candidate `142` is accepted | Is substring presence actually the task's correctness criterion? |
| `first_num` / `last_num` | `1,234` becomes `1` / `234` | Does the extraction rule handle the dataset's answer format? |
| `median` on binary correctness | 60% and 90% accuracy both become `1` | Is median correctness the intended target, or do you need mean accuracy? |

`boxed` falls back to last-number extraction when no box is found. Validate its
fallback on representative outputs. Numeric metric parsing can remove commas,
but it happens **after** extraction; it cannot recover `1,234` once an extractor
has selected `234`. See [metric semantics](metric_semantics.md).

For a dataset whose specification treats the complete output as a numeric answer,
`strict_exact` + `exact_match` + `micro` is one possible baseline. For free-form
reasoning, structured answers, spans or multilingual formats, validate extraction
against labeled examples or supply a reviewed adapter. No single baseline suits
all these tasks.

## Separate a decision analysis from a stress test

- Main analysis: only rules justified for the task, with rationale and exclusions.
- Optional stress analysis: permissive, legacy or deliberately lossy rules,
  reported separately with their purpose.
- Keep the family fixed when comparing models. Do not remove a rule because it
  hurts a preferred model, or add one to manufacture sensitivity.
- Inspect per-item correctness and the endpoint rules. A wide range driven by
  unsuitable rules is a configuration problem, not evidence of a useful reversal.

## Read the result literally

With 90% vs 60% accuracy, micro aggregation gives margin `3/10`. Adding binary
median gives another margin `0`: the band is `[0, 3/10]`, support is `1/2`, and
the strict claim is `UNIDENTIFIABLE`. This is **lead plus tie**, with zero
reversed protocols. Strict reversal requires a negative and a positive margin.

`UNIDENTIFIABLE` describes the supplied strict claim and family. Its support
fraction is a count over those rules. Exact fractions and hashes support replay;
reference correctness, sample representativeness and rule suitability require
their own evidence.

Use the [case template](case_study_template.md) to record the practical decision,
including cases where the tool confirms the original choice.
