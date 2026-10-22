# Professional and generalized editions

Both editions use the same versioned, exact audit and replay core. They have
separate launchers and user bundles. The original 0.5.0 release remains available
as the archived AI evaluation baseline; existing tags and historical results are
preserved.

Version 1.0.0 adds a Windows portable package requiring no Python installation,
validated canonical-data exports, protected NPZ preprocessing and bounded local
HTTP handling. The portable generalized profile contains the three built-in
domains. Use the generalized source bundle for editable adapters and the
measurement-lab example. See the [release evaluation](release_1.0.0.md).

Version 0.6.1 adds a guided first-use interface to both profiles. Open
`WELCOME.html` in either edition bundle to explore exact saved examples without
installation. Start that edition's local app to read your own files or adjust
rules. The preview clearly labels example data and explains the next step.

Version 0.9.0 adds Windows launcher interpreter detection and the fragility-resource prototype. Version 0.8.0 adds the **Ranking audit** page and the shared report layer. Version 0.7.0 adds **Adoption check** to the local app. The professional profile
uses text targets; the generalized profile also supports separate segmentation
class objectives and multiple numeric metrics. Both share the decision core and
replay format. See [the workflow guide](decision_workflow.md).

| | Professional: AI evaluation | Generalized: domain applications |
| --- | --- | --- |
| Intended use | Archived text model outputs and explicit benchmark scoring | Paired domain measurements and editable adapters |
| Browser domains | Original `text` domain | Text, segmentation counts, recorded scalar metrics; trusted registered extensions |
| Policy choices | Original extraction/correctness/aggregation choices | Adapter-specific algorithms, targets and parameters |
| Existing library | Frozen default 80-policy family, exact endpoints, certificates and experimental review APIs | Same core, plus the `AuditDomain` registration contract |
| Source-folder launcher | `start_professional.cmd` | `start_generalized.cmd` |
| Command | `python -m robustband ui --edition professional` | `python -m robustband ui --edition generalized` |

The professional profile keeps its domain list focused on the original text
evaluator. CLI operations can also use `--edition professional` **before** the
subcommand. General-domain audit, template and replay requests are rejected under
that profile. Select scientifically appropriate original policies; the example
starts with two explicitly chosen policies, while `build_family()` remains 80.
The shared exact core is tested in both editions. The profile name does not
establish annotation correctness, policy validity or independent human review.

```bash
python -m robustband --edition professional demo --output audit-demo
python -m robustband --edition professional audit paired.csv --parses last_num boxed --metrics exact_match --aggs micro --output audit-results
python -m robustband --edition professional verify audit-results/report.json
```

## Generalized edition: a working adaptation example

The source-folder `start_generalized.cmd` launches the supplied editable
`examples/measurement_lab.py` adapter when present. It adds **Measurement lab**
to the three standard domains. An installed core wheel provides the three
standard adapters; use the downloaded source example to add the lab:

```bash
python examples/measurement_lab.py ui
```

The lab provides actual algorithm and parameter controls:

- `algorithms`: choose mean, median and/or trimmed mean.
- `trim_each_side`: exact integer count removed from sorted measurements.
- `trim_side`: remove both ends, the upper end, or the lower end.
- `minimum_advantage`: exact nonnegative decimal threshold in supplied score
  units. The strict claim is A's oriented advantage **greater than** this value.
- `note`: retain the reason for the declared policy choices.

Trimming occurs separately within each model; selected observations may differ.
That choice changes the estimand and requires justification. This example
illustrates customization and does not establish a better algorithm. Declare
algorithms/parameters before using outcomes to choose them.

Numeric parameters stay decimal strings from the browser through replay. A
threshold of `0.9999999999999999999999` is distinct from `1`. Algorithms, all
parameters, core hashes and the extension's source hash are saved in JSON.
Changing extension code or recorded settings causes verification to fail until
a new report is generated with that implementation.

```bash
python examples/measurement_lab.py demo --domain measurement_lab --output audit-demo/lab
python examples/measurement_lab.py verify audit-demo/lab/report.json
python examples/measurement_lab.py run metrics.csv --domain measurement_lab --policy my-policies.json --output audit-results
```

Example `my-policies.json`:

```json
{
  "algorithms": ["mean", "trimmed_mean"],
  "trim_each_side": "1",
  "trim_side": "both",
  "minimum_advantage": "0.2",
  "note": "Declared before comparing outcomes; threshold uses the supplied units."
}
```

Copy and modify the adapter to add a domain's calculations or supported
algorithms. Give it a unique domain ID/report schema, validate its parameters,
preserve paired context, and bind its scoring source in replay. Its metadata
generates the shared UI; JSON policy files provide the same settings for
automation. Keep optional image, model or database dependencies in external
preprocessing tools. See [domain contracts](domains.md).

Supported metadata controls are checkbox families, class-index selection,
single-choice selectors, decimal parameter strings and free text. The adapter
performs authoritative validation; the UI does not infer sensible ranges or
scientific applicability. Extending that vocabulary can support future domains
without duplicating the HTTP server, report export or exact band calculation.

## Verification and evidence

Edition tests check domain isolation, unchanged default protocols, shared exact
results, user algorithm selection, parameter validation and extension tampering.
Separate browser receipts cover the professional profile, the standard general
profile and the editable extension. These are automated engineering checks.
Author-local domain trials are application evidence and remain separate from
independent user adoption. The public 1.0.0 repository starts with a clean source
history; prior development history is retained separately.
