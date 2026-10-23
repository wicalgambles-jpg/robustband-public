# Technical feedback follow-up

Date: 2026-10-23. Candidate changes after v1.0.1; published tags/assets are
preserved. This follow-up addresses technical feedback from a source review
and small examples. That review did not run the whole suite or test the desktop
release and is not recorded as a complete independent first-use trial.

## Verified observations

| Observation | Check | Candidate change |
|---|---|---|
| `contains` accepts `142` for reference `42` | Reproduced | Selected-rule caution before running and in the exported HTML |
| Number extraction splits `1,234` | Reproduced | Format/fallback caution and a rule-selection guide |
| Binary median can tie 90% and 60% | Reproduced; `[0, 3/10]`, no reversed protocol | Lead-plus-tie headline, distinct from strict reversal |
| 80 combinations are not 80 justified rules | Library default is 80; guided text default is 2 | Describe the default as a historical sensitivity/stress family |
| `Production/Stable` maturity is premature | Present in v1.0.1 metadata | Beta classifier and status text |
| Resource archive lacks scale and observed paired flips | Existing gates remain unmet | Report observations without claiming sample size explains missing flips |

The parser, metric, aggregation, claim, core and rational scorer sources remain
byte-identical after LF normalization to v1.0.1. This candidate explains rule
consequences; it does not silently redefine them. Existing JSON audit verdicts
and numerical fields remain unchanged. HTML and metadata gain clearer wording.

The optional multi-layer demo description moves from the README to
[technical documentation](tooling_certificate.md). The landing page leads with
using the tool and interpreting the result.

## Next evidence to collect

Start with one real archived-answer comparison and a user who has an actual
selection or evaluation decision. Fix the task, data provenance, reference-label
checks and justified rule family before viewing rankings. Use the
[case record](case_study_template.md) to capture:

1. What the user planned to do before the audit.
2. Installation and first-result time, errors, confusion and assistance needed.
3. What the audit found under justified rules, with ties and reversals separated.
4. What the user actually did afterward, and the evidence connecting that action
   to the finding. An unchanged decision is a valid outcome.

The [use-case issue form](../.github/ISSUE_TEMPLATE/use-case.yml) provides a short
entry point. Approved redacted data can be used where a full report cannot be
shared. A completed automated test matrix supplies engineering evidence; the
user task and observed outcome supply practical-use evidence. The latter is
still open.
