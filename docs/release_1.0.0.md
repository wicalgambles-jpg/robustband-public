# 1.0.0 evaluation and release scope

Date: 2026-10-21. The release preserves the frozen 0.8.0 numerical scoring sources.
The main workflows are paired comparison, adoption criteria and multi-model
ranking. Review planning and compiled-score experiments retain their separate
research API status.

## Assessment-driven changes

The [0.9.0 baseline receipt](../results/release_assessment_0.9.0.json) records an
actual 361-test run with 2,128/2,128 statements covered. Additional disposable
probes reproduced source-file overwrite in NPZ conversion and acceptance of
duplicate HTTP JSON keys. Source inspection also identified unbounded HTTP
workers, authentication after upload, missing NPZ allocation budgets and long
expanded adoption forms.

| Area | 1.0.0 change | Executed evidence |
|---|---|---|
| Exact core and regressions | Frozen scoring retained; conversion, disk failure and request-boundary cases added | 390 tests, 2,309/2,309 statements; `results/quality_gate_1.0.0.json` |
| Standard conversion | Four table contracts, exact decimal/integer retention, explicit mapping/omissions, reload comparison and manifests | Core conversion tests and browser downloads |
| NPZ conversion | Source protection, explicit void mask, archive/pixel/header budgets, full pairing and reference checks | 26 acceptance scenarios; `results/converter_acceptance_1.0.0.json` |
| GPU interoperability | CUDA argmax and counts → NPZ → converter → exact audit and replay | RTX 4060 Laptop, driver 595.79, CUDA runtime 12.9, CuPy 14.2.0; 2/8/64 classes with void pixels; `results/gpu_interoperability_1.0.0.json` |
| Local service | Eight active workers, bounded queue/read timeout, early authentication, strict framing/JSON and 64-level nesting limit | Actual HTTP tests for busy recovery, incomplete uploads, duplicate headers/keys and foreign sessions |
| Browser use | Shared visual polish, collapsible adoption stages, keyboard reopening, validated export and session stop | Six browser variants: comparison in three profiles, adoption in two, ranking; desktop/mobile and reflow checks; no script exceptions |
| Windows portable | Bundled runtime, professional/generalized launchers, replay sources retained | Nine executable checks with system-only PATH and Unicode/space path; `results/portable_acceptance_1.0.0.json` |
| Installable package | Dependency-free wheel and source rebuild | Fresh offline installs from wheel and rebuilt sdist; `results/distribution_check_1.0.0.json` in release assets |

Each receipt states its environment and the source identities it covers. Browser
receipts are `local_ui_smoke_*1.0.0.json`, `decision_ui_*1.0.0.json` and
`matrix_ui_1.0.0.json`. GitHub Actions supplies separate Linux/Windows/macOS ×
Python 3.9/3.11/3.13 evidence, Linux browser checks, Windows/Linux converter
checks, a Windows portable build and offline distribution verification.

## Public snapshot

`robustband-public` starts with the reviewed 1.0.0 source snapshot. The earlier
development repository and its history remain private. Internal preparation
files, private research-note identities, unpublished source data and credentials
are excluded. Historical review cases are supplied as explicitly described
public projections: numerical cases, certificates and measured timings are
retained; private note metadata is omitted. The proof verifier recomputes all 210
feasible plans/root certificates without running the optimizer.

## Evidence boundaries and follow-up

CUDA evidence covers the named hardware and synthetic conversion pipeline.
Auditing uses CPU exact arithmetic. The portable test runs on this Windows host
with Python removed from PATH; it is not a separate clean virtual machine.
Windows binaries are unsigned. Other operating systems use source/wheel packages.

Automated browser checks establish implemented interactions, layout checks and
script behavior. They do not establish independent human ease of use. No independent
user trial has been measured. The [user trial protocol](user_trials.md) specifies
how future evidence will be collected without substituting author-local trials
or scripted runs for external users.

Protocol ranges describe recorded data and selected rules. They are not confidence
intervals or guarantees of valid annotations, scientific policy choices or model
quality. See [security and support](../SECURITY.md) for local session and sharing
behavior.
