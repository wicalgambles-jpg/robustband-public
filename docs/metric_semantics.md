# Built-in text metric semantics

The protocol names below retain the frozen scoring behavior used by existing
releases. All numeric thresholds are compared using exact decimal-to-rational
arithmetic.

| Protocol | Acceptance rule |
|---|---|
| `exact_match` | Lowercase text with stripped/collapsed whitespace is equal, or both values parse as finite decimals with absolute difference ≤ `1e-9` |
| `numeric_tol` | Both values parse as finite decimals with absolute difference ≤ the declared `tol` (default `1e-3`); if either does not parse, fall back to `exact_match` |
| `contains` | The nonempty normalized reference occurs in the normalized candidate |
| `f1_token` | Normalized whitespace-token F1 is at least `1/2`, evaluated as an exact integer inequality; an empty side is rejected |

Numeric parsing removes commas, dollar signs and percent signs before decimal
conversion. It does not rescale percentages. For example, `"50%"` parses as 50.
`exact_match` keeps its fixed `1e-9` numeric tolerance even if the shared metric
function signature receives a `tol` argument; `numeric_tol` uses that argument.

| Candidate vs reference `"1"` | `exact_match` | default `numeric_tol` |
|---|---|---|
| `1.0000000005` | accept | accept |
| `1.000000001` | accept (boundary) | accept |
| `1.0000000010000000001` | reject | accept |
| `1.001` | reject | accept (boundary) |
| `1.0010000000000000001` | reject | reject |

An exact rational computation applies the declared acceptance rule, including its
tolerance. It does not imply a zero-tolerance metric. The 1.0.1 patch documents
and tests these boundaries without changing the frozen scorer sources, the
default 80-protocol family or published numerical results.
