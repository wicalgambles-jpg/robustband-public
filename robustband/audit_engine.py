# SPDX-License-Identifier: MIT
"""Domain-independent exact decisions and replay envelopes.

Adapters provide exact scores and explicitly oriented margins. Positive margins
always support the declared preference for A, including lower-is-better metrics.
"""
from decimal import Decimal, localcontext
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

from . import __version__

MAX_EXACT_BITS = 12000
EXPLANATIONS = {
    "ROBUST": "Every declared protocol supports the preference for A on these records.",
    "REFUTED": "No declared protocol supports the preference for A. Ties do not establish a preference for B.",
    "UNIDENTIFIABLE": "Some declared protocols support the preference for A and others do not.",
}
STRICT_RANK_EXPLANATIONS = {
    "ROBUST": "Every declared protocol supports A > B on these records.",
    "REFUTED": "No declared protocol supports A > B. Ties do not establish B > A.",
    "UNIDENTIFIABLE": "Some declared protocols support A > B and others do not.",
}
LIMITS = ["The result is conditional on the declared protocols and supplied records.",
          "The support fraction is not a probability or confidence level.",
          "This audit does not run model inference, human adjudication or population inference."]


def validate_names(model_a, model_b):
    if (not isinstance(model_a, str) or not model_a.strip() or
            not isinstance(model_b, str) or not model_b.strip() or model_a == model_b):
        raise ValueError("Provide two distinct, nonempty model names.")


def exact(value):
    """Bound serialized rational size without rounding a decision."""
    if max(value.numerator.bit_length(), value.denominator.bit_length()) > MAX_EXACT_BITS:
        raise ValueError("Exact fraction is too large for a readable replay record; narrow the target or use pooled aggregation.")
    return str(value)


def display(value, percent=False):
    """Readable display only; decisions use the original rational."""
    with localcontext() as context:
        context.prec = 12
        number = Decimal(value.numerator) / Decimal(value.denominator)
        if percent:
            number *= 100
        return format(number, ".8g")


def assemble(schema, rows, family, model_a, model_b, configurations, sources,
             warnings, limits, explanations=None):
    """Build the common contract consumed by HTML, CLI and all replay adapters."""
    margins = [Fraction(c["margin"]) for c in configurations]
    lo, hi = min(margins), max(margins)
    support = sum(m > 0 for m in margins)
    verdict = "ROBUST" if lo > 0 else "REFUTED" if hi <= 0 else "UNIDENTIFIABLE"
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    root = Path(__file__).parent
    return {"schema": schema, "software_version": __version__,
            "claim": {"kind": "strict_rank", "model_a": model_a, "model_b": model_b},
            "family": family, "inputs": rows, "input_sha256": sha256(encoded).hexdigest(),
            "source_sha256_lf": {name: sha256((root / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                                 for name in dict.fromkeys((*sources, "audit_engine.py"))},
            "result": {"n_items": len(rows), "n_protocols": len(configurations),
                       "exact_band": [exact(lo), exact(hi)], "verdict": verdict,
                       "explanation": (explanations or EXPLANATIONS)[verdict], "support_count": support,
                       "support_fraction": str(Fraction(support, len(configurations))),
                       "tie_count": sum(m == 0 for m in margins), "reverse_count": sum(m < 0 for m in margins),
                       "strict_sign_flip": lo < 0 < hi},
            "witnesses": {"minimum": configurations[margins.index(lo)], "maximum": configurations[margins.index(hi)]},
            "configurations": configurations, "warnings": warnings, "limits": limits}
