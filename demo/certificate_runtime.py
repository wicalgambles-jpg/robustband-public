# SPDX-License-Identifier: MIT
"""Select a frozen float certificate by an observed summation behavior.

Python 3.12 changed built-in float sum. Strict comparisons around zero in
the historical float bootstrap can therefore differ, despite identical draws.
Both supported profiles are committed and verified; unknown behavior fails.
"""
from pathlib import Path


def float_sum_profile():
    value = sum([1e16, 1.0, -1e16])
    if value == 0.0:
        return "sequential"
    if value == 1.0:
        return "compensated"
    raise RuntimeError("unsupported floating-point sum behavior")


def certificate_path(root):
    suffix = "_sequential" if float_sum_profile() == "sequential" else ""
    return Path(root) / "results" / ("tooling_certificate%s.json" % suffix)
