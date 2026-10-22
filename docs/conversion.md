# Convert paired records without guessing their meaning

The core converter handles the four built-in table contracts: `text`, `scores`,
`segmentation` and `matrix`. CSV and JSONL are supported; confusion matrices use
JSONL. A custom adapter owns its own input contract and preprocessing.

```bash
python -m robustband convert answers.csv --domain text --output answers.jsonl
python -m robustband convert metrics.jsonl --domain scores --to csv --output metrics.csv
python -m robustband convert wide.csv --domain scores --mapping mapping.json --output standard.jsonl
python -m robustband convert models.csv --domain matrix --output models.jsonl
```

Every conversion validates the source, normalizes recognized fields, writes the
chosen format in memory, reloads it through the same domain loader and compares
all normalized records. Numeric scores remain exact decimal strings; integer
counts remain integers. No units, pairing rules or missing values are inferred.
String IDs and canonical defaults follow the documented adapter contracts.

The adjacent `.manifest.json` lists source and output SHA256, explicit mappings,
omitted columns, record/sample totals, source identities and roundtrip status.
Canonical extra columns cause an error unless `--allow-extra-columns` is chosen.
A wide mapping is an explicit selection of columns; other columns are listed.
The manifest contains hashes and settings, while the converted file contains data.

Existing outputs require `--overwrite`; output and sidecar cannot be the input.
Files use individual atomic replacement. A manifest and its data file are two
files, so check their hashes after an interrupted run. Limits: 4 MiB and 5,000
measurement records, including metric expansion for wide inputs.

## Optional segmentation NPZ preprocessing

Install NumPy in a preprocessing environment. This adds no core runtime dependency.
Each folder must contain exactly the same nonempty set of NPZ basenames, with
integer two-dimensional `gt` and `pred` arrays. References must match across A/B.

```bash
python -m pip install numpy
python examples/prepare_segmentation_npz.py cache_a cache_b --n-classes 8 --ignore-index 255 --output paired.jsonl
python -m robustband segment paired.jsonl --output segmentation-audit
python -m robustband verify segmentation-audit/report.json
```

Labels `0..n-classes-1` retain their order. `--class-names` declares names in that
order. `--ignore-index` explicitly excludes a reference void value outside that
range; predictions at those pixels are excluded. A record with no active pixels
is rejected. There is no resizing, label remapping or automatic matching by order.
`--id-suffix` and `--group-separator` declare optional filename rules.

The helper checks archive metadata and NPY headers before loading: at most 256
MiB expanded per archive, 16,777,216 pixels per array, 2–64 classes, no object
arrays, and pickle disabled. It validates all records and the standard-format
roundtrip before saving. `.sources.json` contains basenames and hashes, shape,
dtype, active/ignored counts and the exact class/void rules; absolute paths are
omitted. It never loads checkpoints or generates labels.

Run `python experiments/validate_converters.py` for disposable synthetic acceptance
cases. For actual CUDA interoperability, install compatible CuPy CUDA wheels
following the [CuPy installation guide](https://docs.cupy.dev/en/stable/install.html),
then run `python experiments/validate_gpu.py`. On Windows, use an ASCII-only
environment path if the CUDA compiler cannot read Unicode include paths. The
release receipt records the tested GPU and versions; exact audits run on the CPU.
