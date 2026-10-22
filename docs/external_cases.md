# EvalScope integration cases for 0.4.0

These are exploratory software integration cases from public visualization
records, not new full benchmark evaluations or evidence of external adoption.
The protocol was declared after inspecting the upstream schema and before
computing all score tables. It is not external preregistration.

## Reproduce offline

```bash
python -S experiments/external_cases.py --verify results/external_cases_0.6.1.json
```

The archive includes original files and their license. An optional refresh from
the pinned upstream commit is `python experiments/fetch_external_cases.py`;
the verification command never downloads data or runs model inference.

## Import and alignment

```python
import robustband as rb
adapter = rb.EvalScopeAdapter({
    "qwen-plus": "examples/data/evalscope/qwen-plus/gsm8k_main.jsonl",
    "qwen3-max": "examples/data/evalscope/qwen3-max/gsm8k_main.jsonl",
})
preds = adapter.load()       # raw outputs, gold answers, source metadata
rows = adapter.records()    # also retains recorded scores as Fractions
family = rb.build_family(aggs=["micro"])
result = rb.evaluate(preds, family, rb.RankClaim("qwen3-max", "qwen-plus"))
```

File order differs across models. The adapter checks nonempty identical ID sets
and equal input messages, targets and sample metadata, then sorts by ID. EvalScope
`messages` includes the final assistant completion: this is excluded from the
input context only after checking that it equals `score.prediction`. Earlier
assistant messages, if present, remain part of the input context. Missing fields,
duplicate IDs, drifting contexts, malformed JSON and invalid score values fail.
No intersection, truncation, repaired line or inferred grouping is used.

The new adapter is deliberately separate from the legacy JSONL adapter. The
frozen default 80-configuration family and all built-in score semantics remain
unchanged. This case selects micro aggregation because no group target was
independently justified for these ten samples.

## Results, including ties and negative evidence

For the declared strict claim **qwen3-max > qwen-plus**:

| Case | Pairs | Policies | Exact margin band | Verdict | Strict support |
|---|---:|---:|---|---|---|
| GSM8K public sample | 10 | 5 parsers x 4 metrics x micro = 20 | [-1/10, 0] | REFUTED | 0/20 |
| IFEval public sample | 10 | prompt-level strict / loose = 2 | [-1/10, 0] | REFUTED | 0/2 |

`REFUTED` means that no policy in this declared finite family supports that
strict claim. It does not establish a population ordering, and ties do not prove
the reverse strict claim. A parser that sees no isolated numeric answer gives
both arms zero on several GSM8K policies; such a tie is a diagnostic of that
policy, not evidence of good benchmark validity.

GSM8K raw and cached Band fields agree. All 400 per-item correctness judgments
also match the separate reference parser/metric implementation, and rational
aggregation reproduces every margin. IFEval uses recorded binary **prompt-level**
scores only: exact aggregation is checked, but the instruction graders and the
truthfulness of their recorded outputs are not independently verified.

At epsilon=1/10, unrestricted [-1,1] domains require all 10 reviews in each case.
Candidate-derived independent intervals already have width <=1/10 and need zero
planned reviews. This is an unvalidated coverage assumption, **not demonstrated
human-label savings**. No trusted human labels were supplied.

## Boundaries and provenance

The public samples are ten items each, with API model aliases and no immutable
weight identification. We cannot infer model quality or broad planner efficiency
from them. Imported scores are not human judgments; external-origin data is not
external use of robustband. Source license notices are in
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md), and original file identities
are in [`manifest.json`](../examples/data/evalscope/manifest.json).
The protocol and full report retain all selected policies and item scores.
