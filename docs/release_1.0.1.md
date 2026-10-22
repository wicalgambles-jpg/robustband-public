# 1.0.1 reproducibility patch

Date: 2026-10-22. This patch fixes FR-01 reported by a separately written local
verification run against 1.0.0 (`d483712`). A fresh LF clone reproduced the failure.

## Root cause and correction

The Qwen archive is 1,079,813 bytes with LF and 1,081,132 with CRLF. The difference
is its 1,319 newline characters. Resource-grid v1 normalized the SHA256 but
stored the physical `bytes` count, then compared the complete receipt strictly.
The numerical scores, bands, ranks and gates were unaffected by newline style.

Resource-grid v2 derives `sha256_lf` and `bytes_lf` from the same normalized
bytes. A regression test checks complete-grid equality across newline styles
and confirms that a same-length content edit still changes the file/grid hashes.
The real-input portability gate copies every declared input into disposable LF
and CRLF trees and compares both complete grids with the committed receipt.

## Release evidence

- The current resource and quality receipts are regenerated from a clean LF clone.
- Active release receipt writers use UTF-8/LF and individual atomic replacement.
- Every OS/Python CI test job executes the complete `check_quality.py` gate,
  including resource replay and the real-input newline matrix. Logs and receipts
  are retained as job artifacts.
- Local execution passed 397 tests with 2,312/2,312 package statements covered.
  The supplied separate core/workflow scripts were rerun from copies with only
  repository/output paths changed: 99 and 581 checks passed. Original scripts
  and evidence were retained in their original locations.
- Distribution acceptance also replays the resource receipt and LF/CRLF matrix
  from an unpacked source distribution, outside the working checkout.
- The frozen scorer sources and default 80 protocols remain unchanged.
- The existing `exact_match` tolerance is documented in
  [metric semantics](metric_semantics.md); performance figures are labeled with
  their historical date/environment.

The 1.0.0 tag and historical receipts are preserved. The
[corrected 1.0.0 assessment](release_1.0.0.md) identifies the earlier verification
gap. Independent reimplementation checks are engineering evidence; independent
human first-use trials remain unmeasured.

```bash
python -S experiments/resource_grid.py --verify results/resource_grid_1.0.1.json
python -S experiments/check_resource_portability.py
python submission/check_quality.py
```
