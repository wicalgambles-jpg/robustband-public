# Experimental review planning and related work — 2026-10-12

> **Status: experimental, not part of the main workflow.** The supported path is paired
> audit → adoption check → ranking audit (`python -m robustband audit | decision | matrix`).
> The planner described here ships as a Python API (`robustband.review`), has no measured
> human-label saving on real records, and is excluded from the product claims in the README
> and the release overview. Evidence is synthetic or frozen; no external adoption is claimed.

This work is on `research/review-budget`, starting from `a6dc993` (robustband
0.3.1). It adds candidate software capabilities; it does not establish a new
methodology or change the released 80-configuration scorer.

For the later `research/math-dl-transfer` branch, see the
[shared-price and standalone-proof follow-up](shared_price_review.md). Its additional
capabilities and new experiment are documented separately; the results below
remain the historical review-budget experiment.

## What the literature check supports

The search covered protocol sensitivity, answer extraction, multiverse analysis,
active evaluation, decision-region queries, explorable uncertainty, partial
benchmark decisions and judge calibration. Papers and author-maintained software
were checked on 2026-10-12. This is a focused audit, not an exhaustive novelty proof.

| Primary source | What is already covered | Implication for this project |
|---|---|---|
| [Specification curve analysis (2020)](https://www.nature.com/articles/s41562-020-0912-z), [author's software list](https://urisohn.com/specification-curve/), [Python API](https://aeturrell.github.io/specification_curve/reference/SpecificationCurve.html) | Enumerating justified, statistically valid, non-redundant specifications and showing their results | An enumeration/min-max display is an established approach; specifications must answer the intended question |
| [There Is No Neutral Harness (2026)](https://arxiv.org/html/2608.21382v1), [fragility-grid code](https://github.com/NikolaTesla-007/fragility-grid) | Item-level configuration records, score bands, changed winners and CPU-reproducible analysis | The original robustband phenomenon and broad method overlap directly |
| [Right Answer, Wrong Score (2025)](https://arxiv.org/abs/2503.14996) | Answer-extraction inconsistency and alignment with human judgments | Parser disagreement motivates alignment checks against trusted judgments |
| [Active Testing (ICML 2021)](https://proceedings.mlr.press/v139/kossen21a.html), [code](https://github.com/jlko/active-testing) | Selecting test labels efficiently and correcting selection bias for risk estimation | Active label selection is prior art; our finite-record bounds do not estimate population risk |
| [Near Optimal Bayesian Active Learning for Decision Making (2014)](https://arxiv.org/abs/1402.5886), [Set Selection under Explorable Stochastic Uncertainty (2022)](https://arxiv.org/abs/2211.01097) | Querying uncertain values to determine decisions or minimize query sets | Review planning connects to decision-directed querying and covering formulations |
| [ParEvalLayer (2026)](https://arxiv.org/html/2608.02444v1) | Predeclared comparison policies, paired partial outcomes, continue/abstain reporting and replay | Policy-bound early decisions and abstention are also established; its primary rule is a bootstrap/coverage policy |
| [Causal Judge Evaluation](https://arxiv.org/abs/2512.11150), [CJE software](https://github.com/cimo-labs/cje) | Judge calibration, sampling/calibration uncertainty, assumption diagnostics and oracle-label budgeting | Trusted-review assumptions and label budgets require explicit validation |
| [Speculative Evaluation of Stochastic LLMs (2026)](https://arxiv.org/abs/2609.28560) | Ex-ante rollout allocation and variance reduction under a fixed budget | Rollout allocation complements score reuse; our caching experiment measures repeated offline scoring |

**Relationship to prior work:** protocol sensitivity, interval bounds, query-set
selection and score reuse have established foundations in the sources above.
This prototype integrates those ideas into a finite-record audit workflow. Its
objectives, guarantees and experiments are specified below. The literature review
is focused rather than exhaustive; missing search results are not evidence of novelty.

## The new software capability

The original family mixes two decisions:

1. How to interpret the model's output and judge an item: parser/metric choices.
2. Which evaluation population to emphasize: item-weighted or group-weighted aggregation.

These decisions are now represented separately. A target is an explicit weight
vector on the complete item record. Reviews refine item-level score differences
without changing the target or its denominators.

For item `i`, let the trusted paired correctness difference satisfy
`d_i in [l_i,u_i]`. A declared target `t` has nonnegative rational weights
`w_ti` summing to one. After trusted reviews on `Q`, the completion bounds are

```
L_t(Q) = sum(i in Q) w_ti*d_i + sum(i not in Q) w_ti*l_i
U_t(Q) = sum(i in Q) w_ti*d_i + sum(i not in Q) w_ti*u_i
W_t(Q) = sum(i not in Q) w_ti*(u_i-l_i)
```

The remaining domains are independent per-item possibilities. These bounds are
therefore generally wider than a band over globally consistent scoring protocols.
They are finite-record bounds, not population confidence intervals.

If `L_t > threshold`, that target supports the strict comparison for every
remaining completion. If `U_t <= threshold`, it does not support it. If one
target is guaranteed positive and another guaranteed nonpositive, the result is
`TARGET_CONFLICT`. Future in-domain reviews can only narrow these intervals, so
they cannot reconcile those targets; a stakeholder must commit to a target.
This follows directly from interval monotonicity, with no new-theorem claim.

A plan selects reviews so that **every declared target** has width at most
`epsilon`, regardless of the answers returned by those reviews. This controls
precision, not the probability of finding a desired winner. It can still leave
a close comparison unresolved.

- For one target and unit query costs, sorting weighted interval widths gives a
  minimum-cardinality plan: no `k` items remove more width than the largest `k` contributions.
- In the legacy `plan`, small multiple-target instances use exhaustive subset search to certify the
  minimum cardinality. The default cutoff is 16 ambiguous items, with a maximum of 20.
- The legacy planner uses minimax greedy on larger problems and exposes a per-target lower bound. It
  claim optimality only when their query count matches that lower bound.
- `median` and nonuniform review costs are outside this prototype's supported scope.

The default `unrestricted` domain is `[-1,1]` for every unreviewed binary-score
difference. Optional `candidate` domains use item extrema from candidate scorers.
That option assumes independent adjudication will stay inside those extrema,
including on consensus items. This has not been validated on humans. A review
outside its declared domain raises an error and requires a revised problem;
the software never silently discards that label.

## Reproducible results

The protocol files were written before running the prototypes. The review-budget
experiment uses the same worst-case width objective for every baseline; random
review orders sample only ambiguous items. It is not a numerical comparison with
CJE, Active Testing or ParEvalLayer, whose statistical objectives differ.

| Setting | Exact plan | Minimax greedy | Unweighted width order | Random order, mean | Review all ambiguous items |
|---|---:|---:|---:|---:|---:|
| 100 seeded synthetic cases, 10 items, epsilon=0.10 | 6.95 | 7.01 | 7.43 | 7.445 | 7.54 |
| Real 24-pair record, unrestricted domains, epsilon=0.05 | 24 | 24 | 24 | 24 | 24 |
| Real 24-pair record, candidate domains, epsilon=0.05 | 5 | 5 | 5 | 5.175 | 6 |

Exact planning improves on greedy in only **6/100** synthetic cases. The real
record shows no improvement over the strong deterministic baselines. The five
planned reviews are conditional on candidate-domain coverage and are **not** five
human labels already collected. The default conservative mode needs all 24 items.
This is a feasibility demonstration, not broad efficiency evidence.

On the real record, fixing `last_line_num|exact_match` gives margins `1/24`
(micro), `13/200` (macro_class) and `-1/24` (macro_len). This automatic scorer
diagnostic produces `TARGET_CONFLICT`. It uses an existing scorer, not independent
human adjudication, and shows why merely collecting labels cannot guarantee a
single direction across different target weights.
The demo's class and length groups are derived metadata; their scientific relevance
and weights have not been approved by real evaluation stakeholders.

Every small-case bound is checked against independently enumerated completions,
and every asserted small-case minimum is checked by a separate subset oracle.
The test suite also checks domain violations and modified certificates.
The initial suite had 64 passing tests. With the optimized planner, the combined
suite has **72 passing tests** and **100% package statement coverage (619/619 statements)**.
Coverage is a maintenance gate; the independent completion
and subset oracles are the evidence for the mathematical claims.

## Cached scoring for repeated evaluation

`CompiledScores` snapshots raw-item scores and metadata. Each parser runs once
per item and each parser/metric pair is scored once; repeated resampling invokes
the existing aggregators on cached vectors. Group sizes and median are recomputed
for each resample to preserve the current bootstrap semantics. Registries and
later mutations of caller data do not change the snapshot.

The benchmark compares all serialized Band fields on the same 2,000 paired
bootstrap samples, with the original `20261001` seed and all 80 configurations.
The compilation cost is included in the accelerated elapsed time. Results and
environment details are in `results/compiled_benchmark_2026-10-12.json`.
The observed raw-text scoring time was **170.28 s**, versus **0.85 s** including
compilation, or **200.19x** on this one local run. The SHA-256 digests of all
2,000 serialized Band outputs match. The three existing bootstrap loops now use
this snapshot API, and both existing verifiers pass. The main tooling certificate
and E artifact are byte-identical after normalizing line endings. Gate-1 replay
also exposed two stale pre-0.3.0 single-axis verdicts: metric-only and aggregation-only
cases now correctly read `REFUTED`. These are computed by the original engine,
not by the cached bootstrap path; all margins and bootstrap readings are unchanged.
Caching is a standard engineering technique, so any observed speedup supports
software usefulness rather than method novelty.

## Run it

```bash
python -m coverage run -m pytest -q
python -m coverage report -m
python examples/review_budget.py
python examples/review_budget.py --domain candidate --output results/review_example_candidate.json --template results/review_labels_template.json
python experiments/review_budget.py
python experiments/review_optimization.py --split held_out --external-oracle
python experiments/compiled_benchmark.py
```

Optional `--labels labels.json` reads `{item_id: trusted_difference}`. A reviewer
must judge both arms: `1` means only cot is correct, `-1` means only plain is
correct, and `0` means both correct or both incorrect. Review IDs, values, problem
fingerprint, assumptions and bounds are bound into a recomputable certificate;
that certificate does not authenticate the reviewer or prove the labels true.

## Evidence needed before a methodology paper

Freeze target definitions and domain coverage tests before collecting new labels.
Collect independent adjudications on new, untruncated paired records from several
models and benchmarks, measure the candidate-domain miss rate, and evaluate
decision errors and unresolved cases as well as review cost. Include strong
decision-directed and calibrated-evaluation baselines under matched assumptions.
The initial small gain over greedy was insufficient evidence of a substantive
new algorithm. The optimization follow-up below establishes stronger software
properties and synthetic evidence. A methodology claim still needs a guarantee
or robust real-data advantage that existing mechanisms do not already provide.

## Optimization follow-up: bounded integer planning

`ReviewProblem.plan_optimized(epsilon, reviewed=None, node_budget=5000,
exchange_budget=20000)` optimizes the **same** worst-case width objective with
the same intervals, targets, denominators and unit review costs. It adds no
assumption about which review answers will be returned. The legacy `plan` remains
available and the original experiment remains frozen.

### Mechanism and guarantees

Let `a_ti = w_ti*(u_i-l_i)` after assigning zero width to reviewed items. Planning
can retain a set `K` of unreviewed items subject to `sum(i in K) a_ti <= epsilon`
for every target, maximizing `|K|`. A common denominator converts all coefficients
and epsilon into exact integers. No binary-float threshold is used, even for
arbitrarily close rational boundaries.

The implementation applies these steps:

1. Reproduce legacy minimax greedy with integers, including its tie rule. Keep
   that feasible incumbent, and compare several cheapest-contribution packing
   orders. Therefore the selected review count cannot exceed **legacy greedy**.
2. Drop nonbinding, duplicate and componentwise weaker constraint rows. Group
   items with identical remaining contribution vectors; search their retained
   counts instead of interchangeable subsets. Distinct items remain distinct IDs.
3. For each selected nonnegative pooling of target constraints, sum contributions
   and capacities. Any feasible set must fit the pooled capacity. The maximum
   cardinality that fits a scalar capacity is bounded by sorting its contributions
   ascending and taking the longest affordable prefix. Thus `N - U` is a valid
   review lower bound when `U` bounds retained cardinality among `N` active items.
   This can be much stronger than treating each target separately.
4. Try feasible one-for-two retained-item exchanges, capped by `exchange_budget`
   exact vector comparisons. Each successful exchange removes one review.
5. Search group counts with branch bounds, capped by `node_budget` visited states.
   Exhaustion proves the minimum; a surviving frontier bounds any undiscovered
   retained cardinality. On cutoff, the output reports the feasible review count,
   valid lower bound and their difference. It claims a minimum only when the gap
   is zero. Budgets of zero disable the respective exchange/search step.

These guarantees assume the declared finite-record domains and targets. They do
not prove reviewers correct, domain coverage, or a population-level decision.
The legacy small-instance exhaustive planner can outperform a budget-limited
optimized run; only dominance over legacy **greedy** is unconditional. Node and
comparison budgets limit search work, not wall-clock time, memory, integer bit
length or the polynomial preprocessing work.

The complement is a unit-profit multidimensional knapsack. Portfolio heuristics,
surrogate relaxation and branch-and-bound are established optimization tools;
see the authors' [Multidimensional Knapsack study](https://optimization-online.org/2009/03/2258/).
An optional external comparison uses SciPy's documented [HiGHS MILP interface](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html).
SciPy is not imported by the package or required by the offline unit tests. Solver
success is a numerical cross-check, and each external set is independently checked
with the original rational constraints; it is not substituted for an exact proof.

### Frozen comparison and outcomes

The local protocol is `experiments/review_optimization_protocol.json`. Development
uses seed `20261013`; held-out generation uses `20261107`. After development and
offline tests, implementation, tests and protocol were frozen in commit `1264b7c`
before the held-out outcomes were read. This is a local development split, not an
external preregistration. No case was removed or used to retune this frozen version.
An export-only repair after the run added problem assumptions, input digest and
threshold to reconstruct real cases; algorithm, tests, budgets, plans and timings
were unchanged. A stdlib verifier now checks source hashes, independently
recomputes rational widths and replays both planners and the summary offline.

The held-out file `results/review_optimization_held_out_2026-10-12.json` contains
all 150 reconstructable problems, both planners' sets, rational widths, gaps,
timings, implementation hashes and external solver results. The 100 original
cases and two real-domain cases are regression checks; only the 48 newly generated
cases use the held-out seed. Development results are saved separately.

| Held-out setting | Legacy reviews, mean | Optimized reviews, mean | Cases with fewer reviews | Legacy certified minima | Optimized certified minima | Local elapsed time, legacy / optimized |
|---|---:|---:|---:|---:|---:|---:|
| 36 dense cases, 32/64/128 items and 3/5 targets | 23.2222 | 22.5000 | 23/36 | 1/36 | 29/36 | 0.499 s / 1.503 s |
| 12 grouped cases, 256/512 items and micro/macro targets | 128.8333 | 128.8333 | 0/12 | 12/12 | 12/12 | 3.232 s / 0.406 s |
| 100 original small cases | 6.9500 | 6.9500 | 0/100 | 100/100 | 100/100 | 0.057 s / 0.039 s |
| Real conservative domains | 24 | 24 | 0/1 | 1/1 | 1/1 | 0.0029 s / 0.0008 s |
| Real candidate domains, conditional | 5 | 5 | 0/1 | 1/1 | 1/1 | 0.0005 s / 0.0005 s |

The dense review reduction is **3.11%** and at most two items in any case. Its mean
certified optimality gap falls from **4.1944 to 0.25** (94.04% smaller). Seven
searches hit their node budget; their remaining gaps are reported. The optimized
sets match the external numerical optimum on **33/36** dense cases, including
four whose optimality the internal budgeted search does not prove. Three dense
sets still require more reviews than the external optimum. All other suites match
the external solution count.

The packing portfolio averages 22.7778 dense reviews, exchanges lower it to
22.6111, and search lowers it to 22.5000. This records which stage improves the
feasible count without treating an ablation as a separately optimized baseline.
Grouped planning is **7.97x faster** with equal review counts. Dense planning is
**3.01x slower** than legacy greedy because it does more optimization and proof
work. The external MILP solver is faster on these suites (0.336 s dense, 0.044 s
grouped), so this result does not establish superiority over a mature optimization
solver. Exact arithmetic, stdlib deployment and explicit cutoff gaps are the
properties of this implementation.

Times are one alternating-order local measurement per case; tiny runtimes should
not be treated as stable performance estimates. Grouped acceleration is measured
for the complete integer planner and is not attributed solely to group search.
Synthetic review counts are algorithmic results, not observed human-review savings.

### Use the improved planner

```python
plan = problem.plan_optimized("1/2", node_budget=5000, exchange_budget=20000)
print(plan["n_reviews"], plan["query_lower_bound"], plan["optimality_gap"])
print(plan["search"])
```

```bash
python -S experiments/review_optimization.py --verify results/review_optimization_held_out_2026-10-12.json
```

The example now defaults to this planner. `--planner legacy` selects the original;
`--node-budget 0 --exchange-budget 0` runs only packing and root bounds. Full
`TARGET_CONFLICT` still returns `choose_target` without an applicable query gap.
Independent all-subset tests check 100 small rational problems at three search
budgets, repeated contribution groups, zero weights/widths, reviewed items,
target conflict and arbitrary-precision thresholds. A 120-item disjoint-target
test proves 60 necessary reviews with zero search nodes; the old per-target bound
only proves 30. Thus the improvements can be automatically checked without human
labels, while human accuracy and scientific novelty remain open empirical questions.
