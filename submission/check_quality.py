# SPDX-License-Identifier: MIT
"""Record executed local release gates, source identities and coverage results.

Nothing here is bound to a particular version: the version, today's date, the test
and statement totals and the newest scoring-semantics record are all read at run
time, so a release bumps one version string and this gate follows.
"""
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robustband import __version__  # noqa: E402


def digest(path):
    return sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def newest_semantics():
    """The highest-versioned frozen scoring record; history stays in the folder."""
    files = list((ROOT / "experiments").glob("scoring_semantics_*.json"))
    assert files, "no frozen scoring-semantics record"
    return max(files, key=lambda path: [int(part) for part in re.findall(r"\d+", path.stem)])


def main():
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    matrix_input = "build/matrix-smoke.csv"
    (ROOT / matrix_input).write_text("sample_id,model,gold,output\nq1,a,42,42\nq1,b,42,7\n", encoding="utf-8")
    matrix_output = "build/matrix-smoke"
    commands = [
        ["-m", "coverage", "run", "--source=robustband", "-m", "pytest", "-q",
         "--basetemp=build/pytest-tmp", "--junitxml=build/pytest.xml"],
        ["-m", "coverage", "report", "-m", "--fail-under=100"],
        ["-m", "coverage", "json", "-o", "build/coverage.json"],
        ["-m", "robustband", "matrix", matrix_input, "--output", matrix_output],
        ["-m", "robustband", "verify", matrix_output + "/report.json"],
        ["-S", "experiments/external_cases.py", "--verify", "results/external_cases_%s.json" % __version__],
        ["-S", "experiments/resource_grid.py", "--verify", "results/resource_grid_%s.json" % __version__],
        ["-S", "experiments/review_dual_benchmark.py", "--verify", "results/review_dual_held_out_public_1.0.0.json"],
        ["demo/verify_tooling_certificate.py"],
        ["demo/verify_certificate.py"],
    ]
    for index, args in enumerate(commands):
        process = subprocess.run([sys.executable] + args, cwd=ROOT, capture_output=True)
        (build / ("quality-gate-%d.log" % index)).write_bytes(process.stdout + process.stderr)
        assert process.returncode == 0, (args, process.stdout.decode("utf-8", "replace")[-3000:])
    xml = ET.parse(build / "pytest.xml").getroot()
    suite = xml.find("testsuite")
    counts = {key: int(suite.get(key)) for key in ("tests", "failures", "errors", "skipped")}
    assert counts["tests"] > 0 and counts["failures"] == counts["errors"] == counts["skipped"] == 0, counts
    coverage = json.loads((build / "coverage.json").read_text(encoding="utf-8"))["totals"]
    assert coverage["num_statements"] > 0
    assert coverage["num_statements"] == coverage["covered_lines"] and coverage["missing_lines"] == 0, coverage
    sources = []
    for root in ("robustband", "tests", "demo", "examples", "experiments", "docs", "submission"):
        for path in sorted((ROOT / root).rglob("*.py")):
            assert path.read_text(encoding="utf-8").splitlines()[0] == "# SPDX-License-Identifier: MIT", path
            sources.append(path.relative_to(ROOT))
    semantics_path = newest_semantics()
    semantics = json.loads(semantics_path.read_text(encoding="utf-8"))
    assert all(digest(ROOT / path) == expected for path, expected in semantics["source_sha256_lf"].items())
    report = {"schema": "robustband.quality_gate/v1", "version": __version__, "date": date.today().isoformat(),
              "platform": platform.platform(), "python": platform.python_version(),
              "tests": counts, "coverage": coverage,
              "executed_commands": [{"python_args": args, "exit_code": 0} for args in commands],
              "all_python_sources_have_first_line_spdx": True,
              "scoring_semantics_record": semantics_path.name,
              "frozen_scoring_sources_unchanged": True,
              "matrix_cli_verified": True,
              "source_sha256_lf": {str(path).replace("\\", "/"): digest(ROOT / path) for path in sources},
              "limits": "Automated local checks; not independent human scientific validation or remote CI evidence"}
    (ROOT / "results" / ("quality_gate_%s.json" % __version__)).write_text(json.dumps(report, indent=2) + "\n",
                                                                           encoding="utf-8")
    print("PASS: %d tests; %d/%d statements; matrix CLI; two artifact verifiers; external cases; "
          "review proofs; SPDX; %s" % (counts["tests"], coverage["covered_lines"], coverage["num_statements"],
                                       semantics_path.name))


if __name__ == "__main__":
    main()
