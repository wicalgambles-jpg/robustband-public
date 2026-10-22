# SPDX-License-Identifier: MIT
"""Fetch only the declared, pinned public EvalScope review records and license."""
from hashlib import sha256
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    protocol = json.loads((ROOT / "experiments/external_cases_protocol.json").read_text(encoding="utf-8"))
    revision = protocol["source_revision"]
    base = "https://raw.githubusercontent.com/modelscope/evalscope/" + revision + "/"
    dest = ROOT / "examples/data/evalscope"
    files = {"LICENSE": dest / "LICENSE-APACHE-2.0.txt"}
    for model in protocol["models"]:
        for cfg in protocol["cases"].values():
            source = "examples/viz/%s/reviews/%s/%s" % (model, model, cfg["source_file"])
            files[source] = dest / model / cfg["source_file"]
    entries = []
    for source, path in files.items():
        data = urllib.request.urlopen(base + source, timeout=30).read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("unexpectedly large external fixture")
        if source != "LICENSE":
            rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
            if len(rows) != 10:
                raise ValueError("pinned sample row count changed")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        entries.append({"source_path": source, "url": base + source,
                        "local_path": path.relative_to(ROOT).as_posix(), "bytes": len(data),
                        "sha256_raw": sha256(data).hexdigest(),
                        "sha256_lf": sha256(data.replace(b"\r\n", b"\n")).hexdigest()})
    manifest = {"schema": "robustband.external_sources/v1", "repository": protocol["source_repository"],
                "revision": revision, "files": entries, "new_inference": False}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Fetched %d pinned files; no model inference" % len(entries))


if __name__ == "__main__":
    main()
