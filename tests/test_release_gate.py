# SPDX-License-Identifier: MIT
"""Release regressions: reject unexpected skips and changed float profiles."""
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(relative):
    spec = importlib.util.spec_from_file_location("release_regression", ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_quality_gate_accepts_only_named_platform_skips():
    check = module("submission/check_quality.py").check_test_results
    suite = ET.fromstring('<testsuite tests="3" failures="0" errors="0" skipped="2"/>')
    for name in ("test_detector_finds_an_interpreter_and_propagates_it",
                 "test_a_bad_override_falls_through_to_a_working_interpreter"):
        case = ET.SubElement(suite, "testcase", classname="tests.test_launchers", name=name)
        ET.SubElement(case, "skipped", message="cmd.exe launchers")
    assert len(check(suite, "linux")[1]) == 2
    with pytest.raises(AssertionError):
        check(suite, "win32")
    suite.find("testcase").set("name", "unexpected_skip")
    with pytest.raises(AssertionError):
        check(suite, "linux")
    suite = ET.fromstring('<testsuite tests="3" failures="0" errors="0" skipped="0"/>')
    assert check(suite, "win32")[1] == []


def test_float_certificate_dispatch_is_explicit_and_fails_unknown_modes(monkeypatch):
    runtime = module("demo/certificate_runtime.py")
    for summed, profile, filename in ((0.0, "sequential", "tooling_certificate_sequential.json"),
                                       (1.0, "compensated", "tooling_certificate.json")):
        monkeypatch.setattr(runtime, "sum", lambda _: summed, raising=False)
        assert runtime.float_sum_profile() == profile
        assert runtime.certificate_path(ROOT).name == filename
    monkeypatch.setattr(runtime, "sum", lambda _: 2.0)
    with pytest.raises(RuntimeError, match="unsupported"):
        runtime.certificate_path(ROOT)
