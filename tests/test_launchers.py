# SPDX-License-Identifier: MIT
"""Windows launchers: detection rules, propagation, file hygiene and packaging."""
import os
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAUNCHERS = ("start_robustband.cmd", "start_professional.cmd", "start_generalized.cmd")
DETECTOR = "_detect_python.cmd"
WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe launchers")


def lines(name):
    return [line.strip() for line in (ROOT / name).read_text(encoding="ascii").splitlines()]


@pytest.mark.parametrize("name", LAUNCHERS)
def test_launcher_detects_python_before_starting(name):
    body = lines(name)
    detect = next(index for index, line in enumerate(body) if line == 'call "%~dp0_detect_python.cmd"')
    starts = [index for index, line in enumerate(body)
              if "-m robustband" in line and not line.startswith(("echo", "rem"))]
    assert starts, name
    assert detect < starts[0]
    assert body[detect + 1] == "if errorlevel 1 exit /b 1"


def test_detector_has_override_version_check_and_guidance():
    text = (ROOT / DETECTOR).read_text(encoding="ascii")
    assert "ROBUSTBAND_PYTHON" in text
    assert "sys.version_info >= (3, 9)" in text
    assert "call :accept" in text
    assert "https://www.python.org/downloads/windows/" in text
    assert "pause" in text


@pytest.mark.parametrize("name", LAUNCHERS + (DETECTOR,))
def test_cmd_files_are_ascii_crlf_without_bom(name):
    data = (ROOT / name).read_bytes()
    assert data.isascii(), name
    assert not data.startswith(b"\xef\xbb\xbf"), name
    assert data.count(b"\n") == data.count(b"\r\n"), name
    assert data.splitlines()[0].lower().startswith((b"@echo off", b"@rem")), name


def test_detector_and_launchers_are_declared_in_the_manifest():
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert DETECTOR in manifest
    for name in LAUNCHERS:
        assert name in manifest


@WINDOWS_ONLY
def test_detector_finds_an_interpreter_and_propagates_it(tmp_path):
    wrapper = tmp_path / "probe.cmd"
    wrapper.write_text(
        "@echo off\r\n"
        'call "%~1\\_detect_python.cmd"\r\n'
        "echo CODE=%errorlevel%\r\n"
        "echo PY=[%ROBUSTBAND_PY%]\r\n",
        encoding="ascii")
    result = subprocess.run(["cmd", "/c", str(wrapper), str(ROOT)], capture_output=True, text=True,
                            input="\n", timeout=120)
    assert result.returncode == 0, result.stderr
    assert "[robustband] Python:" in result.stdout
    assert "CODE=0" in result.stdout
    assert re.search(r"PY=\[(?!\])", result.stdout), result.stdout


@WINDOWS_ONLY
def test_a_bad_override_falls_through_to_a_working_interpreter(tmp_path):
    wrapper = tmp_path / "probe.cmd"
    wrapper.write_text(
        "@echo off\r\n"
        'call "%~1\\_detect_python.cmd"\r\n'
        "echo CODE=%errorlevel%\r\n",
        encoding="ascii")
    env = dict(os.environ, ROBUSTBAND_PYTHON=r"C:\does-not-exist\python.exe")
    result = subprocess.run(["cmd", "/c", str(wrapper), str(ROOT)], capture_output=True, text=True,
                            env=env, input="\n", timeout=120)
    assert result.returncode == 0, result.stderr
    assert "CODE=0" in result.stdout
    assert "does-not-exist" not in result.stdout
