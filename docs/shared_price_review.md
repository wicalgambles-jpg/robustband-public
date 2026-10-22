# Shared prices and finite review certificates

## Implemented mechanism

`ReviewProblem.plan_refined(epsilon, reviewed=None, node_budget=5000,
exchange_budget=20000, pricing_rounds=8)` retains the existing problem definition.
The V1 `plan_optimized` remains available. Its plans and diagnostics were replayed
on all 198 prior cases and are unchanged.

The refined planner first computes the same V1 packing and exchanges. When the
root bound already proves that incumbent optimal, adaptive pricing is skipped.
Otherwise it searches shared nonnegative target prices. The guide uses coordinate
updates of a hinge objective followed by projected subgradient updates, because
coordinate descent alone can stop at a nonglobal nonsmooth minimum. For each of
the two starting directions it performs at most `pricing_rounds` coordinate
sweeps and `16*pricing_rounds` subgradient steps. Normalized prices are quantized
to integer directions with coordinates at most 4096 and common factors removed.

Clipping contributions to capacity is used **only inside the float guide** to
avoid overflow in normalization. The feasible sets, new scalar bounds, search and
certificate all use the unchanged original rational contributions. Very large
integer inputs and deliberately poor guidance are checked in the offline tests.
New price orders compete with the existing feasible incumbent; at most six new
directions are retained for branch bounds. Original bounds and group ordering
remain. No success of the numerical optimizer is needed for a valid proof.

Pricing adds preprocessing work even though the search node cap stays fixed.
The reported timings include every pricing pass and certificate construction.
The algorithm remains stdlib-only, with exponential worst-case search and no
polynomial-time optimum guarantee.

## Exact standalone lower bound

**Claim.** Fix any valid ReviewProblem, any in-domain trusted reviews already
provided, any rational `epsilon >= 0`, and any nonnegative rational price `p_t`
for every declared target. Put `a_ti = w_ti*(u_i-l_i)`, assigning zero width to
already reviewed items. Define

```
c_i = sum_t p_t*a_ti
B(p) = epsilon*sum_t p_t + sum_i max(0, 1-c_i)
LB(p) = max(0, n-floor(B(p)))
```

Every additional review set meeting all declared width constraints has size at
least `LB(p)`, irrespective of the answers those reviews reveal.

**Proof.** For any feasible retained-item vector `x_i in {0,1}`, the constraints
give `sum_i c_i*x_i <= epsilon*sum_t p_t`. Also
`(1-c_i)*x_i <= max(0,1-c_i)` termwise. Adding proves `sum_i x_i <= B(p)`.
The left side is an integer, so it is at most `floor(B(p))`. Its complement is
the additional review count; reviewed and zero-width items are free retained
entries and do not become new queries. Clamping the lower bound to zero is valid.

This is standard weak duality specialized to the finite width problem, not a
new theorem claim. See [Boyd and Vandenberghe's duality notes](https://stanford.edu/class/ee364a/lectures/duality.pdf).
Independent optimization certificates also have direct prior work, including
[Verifying Integer Programming Results](https://arxiv.org/abs/1611.08832).

The price vector plus the problem identity, reviewed values, epsilon and exact
`B(p)` is a `robustband.review_lower_bound/v1` certificate. Verification computes
the inequality in `O(n*number_of_targets)` rational operations and calls neither
pricing nor search. Its arithmetic bit cost depends on the declared rationals.
Combine a verified lower bound with an independently checked feasible set of
the same size to prove a minimum. A weaker root certificate does not certify a
stronger search-derived minimum.

**Limitation witnessed by two triangles.** Six items, interval `[0,1]` each, and
six targets corresponding to the edges of two disjoint triangles. Each edge
assigns weight `1/2` to its endpoints, epsilon is `1/2`. At most one vertex per
triangle can be retained, so four reviews are necessary and sufficient. The
fractional vector `x_i=1/2` meets every constraint and retains mass three.
Consequently no hinge-dual root certificate can prove more than three necessary
reviews. The implemented planner finds and proves four with 16 visited states;
its standalone root certificate correctly proves only three. Integer cuts or a
branch proof are needed to close such integrality gaps.

## Frozen comparison

The protocol is `experiments/review_dual_protocol.json`. Development seed is
`20261014`; new held-out seed is `20261123`. Each dense size includes all four
combinations of 3/5 targets and epsilon 1/2 or 1, with four repetitions. Domains,
unit costs, target weights and query precision are identical between planners.
No held-out outcomes were used to retune the frozen version.

The held-out artifact contains **210** reconstructable cases: 60 fresh cases,
100 original small regressions, 48 previously observed larger regressions and
two existing real-domain cases. Development has 60 separate cases. External
HiGHS returns a feasible numerical optimum on all cases; every external set is
checked in original rational arithmetic. It is a numerical cross-check, not a
replacement for the exact certificate or a human reviewer.

| Suite | V1 reviews, mean | Refined reviews, mean | Cases reduced / increased | V1 / refined certified minima | Standalone minima | Local time, V1 / refined |
|---|---:|---:|---:|---:|---:|---:|
| Fresh dense, 48 cases | 22.8750 | 22.7708 | 4 / 0 | 38 / 46 | 38 | 2.699 s / 2.278 s |
| Fresh grouped, 12 cases | 128.8333 | 128.8333 | 0 / 0 | 12 / 12 | 12 | 0.409 s / 0.470 s |
| Original small, 100 cases | 6.9500 | 6.9500 | 0 / 0 | 100 / 100 | 66 | 0.035 s / 0.173 s |
| Previous dense, 36 cases; regression only | 22.5000 | 22.4167 | 3 / 0 | 29 / 36 | 30 | 1.498 s / 1.045 s |
| Previous grouped, 12 cases; regression only | 128.8333 | 128.8333 | 0 / 0 | 12 / 12 | 12 | 0.407 s / 0.468 s |
| Existing real unrestricted / candidate | 24 / 5 | 24 / 5 | 0 / 0 | 2 / 2 | 2 | Both below 2 ms per case |

On fresh dense cases the review reduction over V1 is **0.455%**, five reviews
total. The mean certified gap falls from 0.25 to 0.04167. Search nodes fall from
67,065 to 16,463 (**75.45% fewer**), and planning time is **15.59% lower**. All
48 chosen counts match the external numerical optimum, while two remain
uncertified by the internal budgeted search. This does not justify calling all
48 internally proved minima.

For the 38 fresh dense sets certified by a standalone root bound, checking those
certificates is **24.26x faster** than rerunning refined planning on the same
subset (sums of per-case timings). This compares proof verification with full
planning, not two solvers for the same computational task. Full-case root
certificate verification takes about 0.050 s in total. Grouped certificate
checks similarly take about 0.039 s and are 12.06x faster than replanning.

The grouped planner takes **14.95% longer** than V1, and tiny-case planning is
about 4.92x slower (means 0.35 ms versus 1.73 ms). Proof generation costs time;
there is no universal speedup. These are medians of three alternating-order
measurements on one machine. The external MILP baseline remains mature software;
this result does not claim to outperform it globally.

The protocol also lists legacy planning. Its count-only supplemental comparison
was run on the same 60 fresh frozen cases after the primary benchmark, without
retuning. Fresh dense legacy mean is 23.5625 versus refined 22.7708 (**3.36%**
fewer); its certified minima are 5/48 versus 46/48. It is saved separately as
`results/review_dual_legacy_comparison_2026-10-12.json`, and carries no comparable
timing claim.

All 210 held-out sets have valid root certificates; 160 of them independently
prove the minimum. The other certificates establish only their stated lower
bound. Human labels were not collected, candidate-domain coverage remains
unvalidated, and the real 24-item record has no review-count improvement.

The package has **79 passing tests and 100% statement coverage (748/748)**. New
tests use an independent all-subset oracle on 60 small rational problems at
three budgets, reject altered proofs, forbid optimizer calls during verification,
check deliberately poor guidance and zero-effect representation changes.

## Run and verify without human labels

```python
plan = problem.plan_refined("1/2")
proof = plan["lower_bound_certificate"]
assert problem.verify_lower_bound(proof)
# Proves a minimum when a feasible set meets this independent root bound:
assert proof["query_lower_bound"] <= plan["n_reviews"]
```

```powershell
python examples/review_budget.py --planner refined --domain unrestricted
python examples/review_budget.py --planner refined --domain candidate
python experiments/review_dual_benchmark.py --split held_out --external-oracle
python -S experiments/review_dual_benchmark.py --verify results/review_dual_held_out_public_1.0.0.json
```

The last command checks both planners' feasible widths and all refined root
certificates with exact arithmetic, without any optimization. It does not
independently validate search-only optimality flags or remeasure recorded times.
Public source hashes are checked,
while the math provenance files are not required to verify the numeric proofs.
Float guidance can differ on another platform; the exported exact certificates
remain portable. No SciPy or network is needed for this verification.

## Next feasible research questions

1. **Interaction-aware protocol diagnostics and review groups.** Under an explicitly
   chosen independent product distribution on parser/metric/aggregation choices,
   compute full mixed differences and ANOVA components on the frozen score table.
   [Owen's generalized Sobol work](https://arxiv.org/abs/1205.1774) is direct prior
   art. The new software question is whether high protocol interaction predicts
   when item-by-item review heuristics fail and whether targeted multi-item moves
   close those gaps under matched query costs. An audit distribution over scoring
   choices is not a population distribution or a human-correctness model. Stop if
   this only adds sensitivity plots without improving decisions or planning.
2. **Portable integer branch proofs.** Export a compact covering proof for the eight
   fresh dense minima requiring search, and retain valid frontier-gap proofs for
   the two unresolved cases. Check every group-count branch and exact scalar
   prune without rerunning guidance. The two-triangle example is a falsifiable
   gate: a root-only LP certificate must remain insufficient. Measure proof size,
   verification time and query count jointly, against existing MIP certificates.
3. **Shared, calibrated scoring uncertainty.** Replace independent item domains
   only when a defensible joint uncertainty model is available. A shared scorer
   hypothesis can make one review informative about multiple items, which the
   current independent-domain model forbids. First show synthetic decision-query
   gains with valid coverage; later test misses on independent adjudications.
   Stop if savings rely entirely on assuming the unknown true scorer lies in the
   candidate set. This is OPEN and has not been implemented or human validated.

The most immediate structural research direction is now proof completeness and
protocol interaction, rather than relabeling standard knapsack optimization as a
new method. The measured improvements support the software; scientific novelty
must be checked for each of these more specific contracts.
