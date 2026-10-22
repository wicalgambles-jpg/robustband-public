# SPDX-License-Identifier: MIT
"""Example: use ``robustband`` as a gate in a leaderboard or CI pipeline.

The shipped 24-item paired sample (GSM8K, Qwen2.5-0.5B-Instruct, CoT vs. plain prompting)
is used as the audit subject, so the example runs offline on the repository's own data.

    python examples/band_gate.py            # report the band, always exit 0
    python examples/band_gate.py --strict   # exit 1 when the claim is not identifiable

On this data the canonical claim ``cot > plain`` is **UNIDENTIFIABLE** under the declared
80-configuration scoring family, so ``--strict`` exits 1 by design: that is the tool
doing its job -- a point-estimate leaderboard would have reported a single number.
"""
import pathlib
import sys

import robustband as rb

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "demo" / "data_real"


def load_pairs(root, n=24):
    """Read ``<root>/cot.jsonl`` and ``<root>/plain.jsonl`` and pair the first n rows."""
    preds = rb.JSONLAdapter(root).load()
    if not {"cot", "plain"} <= set(preds):
        raise SystemExit(f"expected cot.jsonl and plain.jsonl under {root}")
    return {m: {"items": preds[m]["items"][:n]} for m in ("cot", "plain")}


def main(argv):
    strict = "--strict" in argv[1:]
    preds = load_pairs(DATA)
    family = rb.build_family()                     # parse x metric x agg = 5 x 4 x 4 = 80
    claim = rb.RankClaim("cot", "plain")
    band = rb.evaluate(preds, family, claim)

    print(f"claim      : {claim.name}")
    print(f"configs    : {band.n_configs}")
    print(f"delta      : ({band.delta[0]:+.6f}, {band.delta[1]:+.6f})")
    print(f"verdict    : {band.verdict}")
    print(f"stability  : {band.stability_fraction:.4f}")
    print(f"breaks     : {len(band.break_set)}/{band.n_configs}")

    cert = rb.certificate.emit(preds, family, claim, band)
    if cert is None:
        print("certificate: none (the claim holds or fails under every declared protocol)")
        return 0
    print(f"certificate: {cert['type']}")
    if cert["type"] == "impossibility_certificate":
        print(f"  supports : {cert['witness_positive']['config']} "
              f"({cert['witness_positive']['margin']:+.6f})")
        print(f"  opposes  : {cert['witness_negative']['config']} "
              f"({cert['witness_negative']['margin']:+.6f})")
        if strict:
            print("\n[gate] FAIL: the claim is not identifiable under the declared protocols.")
            return 1
    else:
        print(f"  minimal counterexample: {cert['config']} ({cert['margin']:+.6f})")
        if strict:
            print("\n[gate] FAIL: the claim does not hold under at least one declared protocol.")
            return 1

    print("\n[gate] OK (strict mode not requested)" if not strict else "\n[gate] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
