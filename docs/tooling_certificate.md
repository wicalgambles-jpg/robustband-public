# Tooling certificate replay

`demo/tooling_certificate.py` emits a single machine-readable JSON artifact
(`results/tooling_certificate.json`, schema `robustband.tooling_certificate/v3`) that
binds four layers:

| layer | content |
|---|---|
| **L1** positive band | the δ-band, verdict, witnesses  |
| **L2** counterexamples | impossibility certificate + minimal counterexample + strongest counterexample + decision hooks D1/D2/D3 |
| **L3** robustness | full-scale score band + paired bootstrap (`P(UNIDENTIFIABLE)`, `P(sign-flip)`) + leave-one-axis subfamilies |
| **L4** certified endpoints | exact-`Fraction` band over the built-in metrics, duplication invariance |

The certificate is **recomputed from hashed input files** (V-source, V0–V8) by
`demo/verify_tooling_certificate.py`, which does **not** trust the artifact's own numbers —
it checks every layer, including the 1319-item score band. The main score band is also
checked with a separate reference implementation; bootstrap checks still share the engine.
Input hashes normalize CRLF to LF so the same text verifies on Windows and Unix.
Schema v3 records the floating summation profile: Python 3.9/3.11 use the
sequential snapshot `results/tooling_certificate_sequential.json`; Python 3.12+
uses the compensated snapshot `results/tooling_certificate.json`. The verifier
detects the sum behavior and strictly replays the corresponding frozen artifact.
Near-zero bootstrap margins differ between these profiles; see
[the 1.0.1 evidence](release_1.0.1.md). Exact rational endpoints are checked
separately.
The repository ships the frozen model outputs for rescoring; it does not currently pin
the model revision and full generation environment needed to reproduce those outputs.
Dataset and model attribution is recorded in `THIRD_PARTY_NOTICES.md`.

```bash
cd demo
python tooling_certificate.py          # writes the runtime's matching certificate
python verify_tooling_certificate.py   # re-derives V-source and V0..V8; prints [VERIFY PASS] (exit 0)
```

