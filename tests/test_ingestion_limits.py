# SPDX-License-Identifier: MIT
"""Bounded ingestion: encoding guidance, CSV positions, limits and concurrency."""
import json
import threading
import time

import pytest

from robustband import cli, local_ui
from robustband.input_utils import MAX_ROWS, read_table
from test_local_ui_cli import request


def test_non_utf8_cli_failure_explains_the_repair(tmp_path, capsys):
    path = tmp_path / "gbk.csv"
    path.write_bytes(b"\xc9\xfa\xb3\xc9,model,gold,output\n")
    assert cli.main(["audit", str(path), "--output", str(tmp_path / "out")]) == 2
    message = capsys.readouterr().err
    assert "Save the file as UTF-8" in message and "byte 0" in message


def test_replacement_characters_are_rejected_with_guidance():
    with pytest.raises(ValueError, match="replacement characters"):
        read_table("sample_id,model,gold,output\nq1,a,42,\ufffd\n", "csv",
                   ("sample_id", "model", "gold", "output"))


def test_csv_errors_report_a_line_and_limits_point_at_the_api():
    with pytest.raises(ValueError, match="Invalid CSV near line"):
        read_table('a,b\n1,"unclosed\n', "csv", ("a", "b"))
    with pytest.raises(ValueError, match="Python API"):
        read_table("a,b\n1,2\n2,3\n", "csv", ("a", "b"), max_rows=1)
    with pytest.raises(ValueError, match="Python API"):
        read_table('{"a":1}\n{"a":2}\n', "jsonl", ("a",), max_rows=1)


def test_the_local_server_serves_a_second_request_while_one_is_blocked(server, monkeypatch):
    gate = threading.Event()
    original = local_ui.preview_domain

    def slow_preview(*args, **kwargs):
        gate.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(local_ui, "preview_domain", slow_preview)
    payload = {"text": "sample_id,prompt,gold,output_a,output_b\nq1,p,42,42,41\n", "format": "csv"}
    results = {}

    def blocked():
        results["preview"] = request(server, "/api/preview", payload)[0]

    worker = threading.Thread(target=blocked, daemon=True)
    worker.start()
    assert local_ui.ThreadingHTTPServer is type(server)
    time.sleep(0.2)                                     # the first request is now blocked
    assert server.edition == "generalized"
    assert request(server, "/api/options")[0] == 200     # a second connection is still served
    gate.set()
    worker.join(timeout=5)
    assert results["preview"] == 200


def test_matrix_preview_rejects_oversized_uploads_with_a_repair_hint():
    server = local_ui.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(server, "/api/matrix/preview",
                                  {"text": "sample_id,model,gold,output\n" + "q1,a,42,42\n" * (MAX_ROWS + 1),
                                   "format": "csv"})
        assert status == 400 and "Python API" in json.loads(body)["error"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
