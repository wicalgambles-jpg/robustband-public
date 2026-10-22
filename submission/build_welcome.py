# SPDX-License-Identifier: MIT
"""Create a standalone, no-install example from the actual UI and exact reports.

Only domain-owned synthetic examples are included. No user files are read.
The page makes no requests: new calculations remain in the local application.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robustband import __version__
from robustband.domains import domain_options, audit_domain, preview_domain, verify_audit
from robustband.input_utils import MAX_BYTES
from robustband.report import render_html


def build(output, edition="generalized", include_lab=False):
    if include_lab:
        from examples.measurement_lab import register
        from robustband.domains import get_domain
        try:
            get_domain("measurement_lab")
        except ValueError:
            register()
    options = {"version": __version__, "edition": edition, "domains": domain_options(edition), "max_bytes": MAX_BYTES}
    examples = {}
    for domain in options["domains"]:
        text, format = domain["example"], domain["example_format"]
        report = audit_domain(domain["id"], text, format, domain["defaults"])
        assert verify_audit(report, edition)
        examples[domain["id"]] = {"preview": preview_domain(domain["id"], text, format),
            "result": {"report": report, "html": render_html(report), "json": json.dumps(report, ensure_ascii=False, indent=2) + "\n"}}
    payload = json.dumps({"schema": "robustband.offline_examples/v1", "options": options, "examples": examples}, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace("&", "\\u0026")
    template = (ROOT / "robustband/ui.html").read_text(encoding="utf-8")
    marker = '<script id="offlineData" type="application/json">{}</script>'
    assert template.count(marker) == 1
    html = template.replace(marker, '<script id="offlineData" type="application/json">' + payload + '</script>')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(html.encode("utf-8"))
    print("Standalone example: %s (%s; %d domains)" % (output.name, edition, len(examples)))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=ROOT / "WELCOME.html")
    parser.add_argument("--edition", choices=("professional", "generalized"), default="generalized")
    parser.add_argument("--include-lab", action="store_true")
    args = parser.parse_args()
    build(args.output, args.edition, args.include_lab)


if __name__ == "__main__":
    main()
