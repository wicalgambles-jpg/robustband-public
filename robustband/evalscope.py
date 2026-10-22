# SPDX-License-Identifier: MIT
"""Strict import of EvalScope review JSONL, including recorded score columns.

Records are paired by sample ID, never file position. Input messages exclude
the final assistant response only after it matches the recorded prediction.
Scores are imported data; importing them does not rerun their upstream grader.
"""
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path

from .adapter import BenchmarkAdapter


def _reject_constant(value):
    raise ValueError("nonstandard JSON numeric constant: " + value)


def _record(row):
    try:
        sample = row["sample_score"]
        identity = sample["sample_id"]
        gold, metadata = row["target"], sample["sample_metadata"]
        prediction = sample["score"]["prediction"]
        values = sample["score"]["value"]
        messages = [(m["role"], m["content"]) for m in row["messages"]]
    except (KeyError, TypeError) as exc:
        raise ValueError("incomplete EvalScope review record") from exc
    if type(identity) not in (int, str) or identity == "":
        raise ValueError("sample_id must be an integer or nonempty string")
    if not isinstance(gold, str) or not isinstance(prediction, str) or not isinstance(metadata, dict):
        raise ValueError("target/prediction must be strings and sample_metadata a mapping")
    if (len(messages) < 2 or any(not isinstance(r, str) or not isinstance(c, str)
                                for r, c in messages)
            or messages[-1] != ("assistant", prediction)):
        raise ValueError("messages must contain inputs followed by the recorded assistant prediction")
    if not isinstance(values, dict) or not values:
        raise ValueError("recorded score values must be a nonempty mapping")
    scores = {}
    for name, value in values.items():
        if not isinstance(name, str) or not name or type(value) not in (int, Decimal):
            raise ValueError("recorded scores must have named numeric values")
        score = Fraction(value)
        if not 0 <= score <= 1:
            raise ValueError("recorded scores must lie in [0,1]")
        scores[name] = score
    return {"sample_id": identity, "raw": prediction, "gold": gold,
            "metadata": metadata, "input_messages": messages[:-1], "scores": scores}


class EvalScopeAdapter(BenchmarkAdapter):
    """Read model -> review-file mappings; enforce identical paired contexts.

    ``records()`` retains exact rational recorded scores. ``load()`` produces
    raw/gold/meta inputs for robustband's scorers; upstream score columns are
    deliberately not substituted for fresh scoring. No grouping is inferred.
    """
    name = "evalscope_review"

    def __init__(self, files):
        self.files = {model: Path(path) for model, path in files.items()}
        if not self.files or any(not isinstance(m, str) or not m for m in self.files):
            raise ValueError("provide at least one named model review file")

    def records(self):
        """Return aligned records, sorted by ID type and value; fail on drift."""
        indexed = {}
        for model, path in self.files.items():
            records = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = _record(json.loads(line, parse_float=Decimal,
                                            parse_constant=_reject_constant))
                identity = record["sample_id"]
                if identity in records:
                    raise ValueError("duplicate sample ID in " + model)
                records[identity] = record
            if not records:
                raise ValueError("empty review file for " + model)
            indexed[model] = records
        first = next(iter(indexed.values()))
        ids = sorted(first, key=lambda i: (type(i).__name__, i))
        context = lambda r: (r["gold"], r["input_messages"], r["metadata"])
        for model, records in indexed.items():
            if set(records) != set(first):
                raise ValueError("sample-ID sets differ for " + model)
            if any(context(records[i]) != context(first[i]) for i in ids):
                raise ValueError("paired input, target or metadata differs for " + model)
        return {model: [records[i] for i in ids] for model, records in indexed.items()}

    def load(self):
        return {model: {"items": [(r["raw"], r["gold"],
                                   {"sample_id": r["sample_id"], "source_metadata": r["metadata"]})
                                  for r in rows]}
                for model, rows in self.records().items()}
