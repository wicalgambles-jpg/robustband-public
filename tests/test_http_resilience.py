# SPDX-License-Identifier: MIT
"""Bounded workers, strict request framing and authentication before upload."""
import http.client
import json
import socket
import sys
from unittest.mock import Mock

import pytest
from robustband import local_ui
from robustband.input_utils import read_table
from test_local_ui_cli import request


def raw(server,body,headers=()):
    client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
    client.putrequest('POST','/api/convert')
    client.putheader('X-Robustband-Token',server.token)
    client.putheader('Content-Type','application/json')
    for k,v in headers: client.putheader(k,v)
    client.endheaders(body)
    response=client.getresponse(); data=response.read(); client.close()
    return response.status,data


@pytest.mark.parametrize('body',[b'{"format":"csv","format":"jsonl"}',b'{"x":NaN}',b'{"x":'+b'['*1500+b'0'+b']'*1500+b'}'])
def test_invalid_json_configuration_is_rejected(server,body):
    assert raw(server,body,[('Content-Length',str(len(body)))])[0]==400
    assert request(server,'/api/options')[0]==200


def test_duplicate_length_and_transfer_encoding_rejected(server):
    assert raw(server,None,[('Content-Length','2'),('Content-Length','2')])[0]==400
    assert raw(server,None,[('Transfer-Encoding','chunked')])[0]==400


def test_unauthenticated_upload_rejected_before_body_read(server):
    client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=1)
    client.request('POST','/api/audit',None,{'Content-Length':'100000'})
    assert client.getresponse().status==403
    client.close()


def test_saturated_workers_retry_and_recover(server):
    for _ in range(local_ui.MAX_CONNECTIONS): assert server.slots.acquire(False)
    try:
        status,headers,body=request(server,'/api/options')
        assert status==503 and headers['Retry-After']=='1' and 'busy' in json.loads(body)['error']
    finally:
        for _ in range(local_ui.MAX_CONNECTIONS): server.slots.release()
    assert request(server,'/api/options')[0]==200


def test_worker_start_failure_and_disconnected_busy_client_release_slot(server,monkeypatch):
    def fail(*args): raise RuntimeError('thread start failed')
    monkeypatch.setattr(local_ui._ThreadingHTTPServer,'process_request',fail)
    with pytest.raises(RuntimeError,match='thread start'):
        server.process_request(Mock(),('127.0.0.1',1))
    for _ in range(local_ui.MAX_CONNECTIONS): assert server.slots.acquire(False)
    fake=Mock(); fake.sendall.side_effect=OSError('disconnected')
    server.process_request(fake,('127.0.0.1',1))
    for _ in range(local_ui.MAX_CONNECTIONS): server.slots.release()


def test_reply_body_disconnect_is_harmless():
    handler=object.__new__(local_ui._Handler)
    handler.send_response=Mock(); handler.send_header=Mock(); handler.end_headers=Mock()
    handler.wfile=Mock(); handler.wfile.write.side_effect=BrokenPipeError()
    handler._send(200,{'ok':True})


def test_rejected_upload_drain_timeout_does_not_start_parsing():
    handler=object.__new__(local_ui._Handler)
    handler.server=Mock(server_port=123,token='secret')
    handler.headers=Mock(); handler.headers.get.return_value='wrong'
    handler._send=Mock(); handler.connection=Mock(); handler.rfile=Mock()
    handler.rfile.read1.side_effect=TimeoutError('not sending a body')
    handler.do_POST()
    assert handler._send.call_args.args[0]==403
    handler.rfile.read1.assert_called_once_with(8192)


def test_malformed_csv_header_and_deep_jsonl_have_positions():
    with pytest.raises(ValueError,match='CSV header near line 1'):
        read_table('x'*150000+'\n','csv')
    with pytest.raises(ValueError,match='JSONL line 1'):
        read_table('['*(sys.getrecursionlimit()+100)+'0'+']'*(sys.getrecursionlimit()+100),'jsonl')
