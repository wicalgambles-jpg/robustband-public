# SPDX-License-Identifier: MIT
"""Edition isolation and a user-owned algorithm/parameter adapter."""
from copy import deepcopy
from fractions import Fraction as F
import json
import threading

import pytest
import robustband as rb
from robustband import domains as dm, local_ui
from robustband.cli import main
from robustband.report import render_html
from robustband.scores import DEMO_CSV, load_scores
from examples import measurement_lab as lab
from test_local_ui_cli import request


def test_professional_edition_keeps_original_domain_and_protocols(tmp_path, capsys):
    assert [d["id"] for d in dm.domain_options("professional")] == ["text"]
    assert len(rb.build_family()) == 80
    assert main(["--edition", "professional", "domains"]) == 0
    assert [d["id"] for d in json.loads(capsys.readouterr().out)] == ["text"]
    output = tmp_path/"report"
    assert main(["--edition","professional","demo","--output",str(output)]) == 0
    assert main(["--edition","professional","verify",str(output/"report.json")]) == 0
    path = tmp_path/"scores.csv"
    path.write_text(DEMO_CSV, encoding="utf-8")
    assert main(["--edition","professional","scores",str(path)]) == 2
    assert main(["--edition","professional","template",str(path),"--domain","scores"]) == 2
    with pytest.raises(ValueError, match="edition"):
        dm.domain_options("unknown")
    with pytest.raises(ValueError, match="professional"):
        dm.verify_audit(dm.audit_domain("scores",DEMO_CSV),"professional")


def test_professional_session_rejects_general_domain_requests():
    server = local_ui.create_server(edition="professional")
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        status,_,body = request(server,"/api/options")
        options = json.loads(body)
        assert status == 200 and options["edition"] == "professional"
        assert [d["id"] for d in options["domains"]] == ["text"]
        status,_,body = request(server,"/api/audit",{"mode":"scores","text":DEMO_CSV})
        assert status == 400 and "professional" in json.loads(body)["error"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_user_algorithms_parameters_and_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(dm,"_DOMAINS",dict(dm._DOMAINS))
    lab.register()
    report = dm.audit_domain("measurement_lab",DEMO_CSV)
    assert dm.verify_audit(report)
    assert report["result"]["exact_band"] == ["-8/3","1"]
    assert report["configurations"][2]["score_a"] == "9"
    assert "examples/measurement_lab.py" in report["extension_source_sha256_lf"]
    settings = deepcopy(lab.DEFAULTS)
    settings.update(algorithms=["trimmed_mean"],minimum_advantage="1",note="<img src=x>")
    threshold = dm.audit_domain("measurement_lab",DEMO_CSV,family=settings,model_a="A<script>")
    assert threshold["result"]["exact_band"] == ["0","0"] and threshold["result"]["verdict"] == "REFUTED"
    html = render_html(threshold)
    assert "&lt;img" in html and "&lt;script&gt;" in html and "strictly exceeds 1 ms" in html
    precise = lab.analyze(load_scores(DEMO_CSV),{**settings,"minimum_advantage":"0.9999999999999999999999"})
    assert precise["result"]["exact_band"] == [str(F(1,10**22))]*2
    assert precise["result"]["verdict"] == "ROBUST"
    settings["trim_side"] = "upper"
    upper = lab.analyze(load_scores(DEMO_CSV),settings)
    assert upper["configurations"][0]["score_a"] == "9"
    settings["trim_side"] = "lower"
    lower = lab.analyze(load_scores(DEMO_CSV),settings)
    assert F(lower["configurations"][0]["margin"]) == F(-11,2)
    settings["trim_each_side"] = "0"
    assert lab.analyze(load_scores(DEMO_CSV),settings)["configurations"][0]["score_a"] == "128/3"
    for key in ("family","extension_source_sha256_lf"):
        changed = deepcopy(report)
        changed[key].clear()
        with pytest.raises(ValueError):
            dm.verify_audit(changed)
    with pytest.raises(ValueError,match="schema"):
        lab.verify({})
    with pytest.raises(ValueError,match="Incomplete"):
        lab.verify({"schema":lab.SCHEMA})
    path = tmp_path/"scores.csv"
    path.write_text(DEMO_CSV,encoding="utf-8")
    policy = tmp_path/"policy.json"
    policy.write_text(json.dumps(lab.DEFAULTS),encoding="utf-8")
    output = tmp_path/"report"
    assert main(["run",str(path),"--domain","measurement_lab","--policy",str(policy),"--output",str(output)]) == 0
    assert main(["verify",str(output/"report.json")]) == 0
    assert [d["id"] for d in dm.domain_options("professional")] == ["text"]


@pytest.mark.parametrize("settings", [
    {}, [], {**lab.DEFAULTS,"algorithms":[]}, {**lab.DEFAULTS,"algorithms":["unknown"]},
    {**lab.DEFAULTS,"trim_each_side":1}, {**lab.DEFAULTS,"trim_each_side":"2"},
    {**lab.DEFAULTS,"trim_side":"none"}, {**lab.DEFAULTS,"minimum_advantage":0.1},
    {**lab.DEFAULTS,"minimum_advantage":"NaN"}, {**lab.DEFAULTS,"minimum_advantage":"invalid"},
    {**lab.DEFAULTS,"minimum_advantage":"-1"}, {**lab.DEFAULTS,"minimum_advantage":"1e129"},
    {**lab.DEFAULTS,"minimum_advantage":"1"*257}, {**lab.DEFAULTS,"note":2},
])
def test_custom_parameters_are_validated_by_the_adapter(settings):
    with pytest.raises(ValueError):
        lab.analyze(load_scores(DEMO_CSV),settings)
