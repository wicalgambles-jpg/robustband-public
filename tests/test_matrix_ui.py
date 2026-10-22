# SPDX-License-Identifier: MIT
"""Ranking audit page and its loopback routes."""
import json
import threading

import pytest

from robustband import local_ui
from robustband.matrix import DEMO_CSV, SCHEMA, verify_matrix_report
from test_local_ui_cli import request


def test_matrix_page_and_options(server):
    status, headers, page = request(server, "/matrix")
    assert status == 200 and "排名审计" in page.decode("utf-8")
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    status, _, body = request(server, "/api/options")
    options = json.loads(body)
    assert options["matrix_example"] == DEMO_CSV
    assert options["matrix_max_models"] == 8 and options["matrix_max_rows"] == 5000
    assert options["matrix_defaults"]["parses"] == ["first_num", "last_num"]


def test_matrix_preview_and_audit_round_trip(server):
    payload = {"text": DEMO_CSV, "format": "csv"}
    status, _, body = request(server, "/api/matrix/preview", payload)
    preview = json.loads(body)
    assert status == 200 and preview["n_models"] == 3 and preview["n_items"] == 1
    payload["family"] = {"parses": ["first_num", "last_num"], "metrics": ["exact_match"], "aggs": ["micro"]}
    status, _, body = request(server, "/api/matrix/audit", payload)
    result = json.loads(body)
    assert status == 200 and result["report"]["schema"] == SCHEMA
    assert result["report"]["result"]["verdict"] == "SENSITIVE"
    assert verify_matrix_report(json.loads(result["json"]))
    assert "排名审计" in result["html"] and "名次" in result["html"]


@pytest.mark.parametrize("path,payload,match", [
    ("/api/matrix/preview", {"text": "sample_id,model,gold,output\nq1,a,42,42\n", "format": "csv"}, "at least two models"),
    ("/api/matrix/audit", {"text": DEMO_CSV, "format": "csv", "family": {"parses": []}}, "Declare parses"),
    ("/api/matrix/audit", {"text": DEMO_CSV, "format": "csv",
                           "family": {"parses": ["first_num"], "metrics": ["exact_match"], "aggs": ["nope"]}},
     "supported option"),
], ids=["one-model", "empty-axis", "unknown-aggregation"])
def test_matrix_routes_report_invalid_input(server, path, payload, match):
    status, _, body = request(server, path, payload)
    assert status == 400 and match in json.loads(body)["error"]


def test_matrix_route_requires_the_session_token(server):
    status, _, body = request(server, "/api/matrix/preview", {"text": DEMO_CSV, "format": "csv"},
                              headers={"X-Robustband-Token": "wrong"})
    assert status == 403 and "launch URL" in json.loads(body)["error"]
    status, _, body = request(server, "/api/matrix/other", {})
    assert status == 404


def test_matrix_is_edition_neutral():
    professional = local_ui.create_server(edition="professional")
    thread = threading.Thread(target=professional.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(professional, "/api/matrix/audit",
                                  {"text": DEMO_CSV, "format": "csv",
                                   "family": {"parses": ["first_num"], "metrics": ["exact_match"], "aggs": ["micro"]}})
        report = json.loads(body)["report"]
        assert status == 200 and report["schema"] == SCHEMA and report["result"]["n_models"] == 3
    finally:
        professional.shutdown()
        thread.join(timeout=5)
        professional.server_close()
