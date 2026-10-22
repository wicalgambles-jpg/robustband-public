# SPDX-License-Identifier: MIT
"""Receipt bytes are portable without changing scoring semantics."""
import json
import pytest
from robustband.storage import write_json_atomic
from robustband.metrics import m_exact, m_numeric_tol


def test_json_receipt_uses_utf8_lf_and_failed_serialization_preserves_output(tmp_path):
    output=tmp_path/'receipt.json'
    value={'label':'中文','embedded':'first\nsecond','count':9007199254740993}
    write_json_atomic(output,value)
    data=output.read_bytes()
    assert data.endswith(b'\n') and b'\r\n' not in data
    assert '中文'.encode('utf-8') in data and json.loads(data)==value
    with pytest.raises(ValueError): write_json_atomic(output,{'bad':float('nan')})
    assert output.read_bytes()==data


@pytest.mark.parametrize('candidate,exact,tolerant',[
    ('1.0000000005',1,1),('1.000000001',1,1),('1.0000000010000000001',0,1),
    ('1.001',0,1),('1.0010000000000000001',0,0)])
def test_documented_numeric_boundaries_preserve_frozen_metrics(candidate,exact,tolerant):
    assert m_exact(candidate,'1')==exact
    assert m_numeric_tol(candidate,'1')==tolerant
