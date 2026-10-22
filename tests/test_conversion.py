# SPDX-License-Identifier: MIT
"""Conversion preserves declared values and protects existing source files."""
from copy import deepcopy
import json
import os

import pytest
from robustband import cli, convert, storage
from robustband.workflow import DEMO_CSV
from robustband.scores import DEMO_CSV as SCORES
from robustband.segmentation import DEMO_JSONL
from robustband.matrix import DEMO_CSV as MATRIX
from robustband.decision import EXAMPLE, EXAMPLE_MAPPING
from test_local_ui_cli import request


@pytest.mark.parametrize('domain,text,format', [('text',DEMO_CSV,'csv'),('scores',SCORES,'csv'),
    ('segmentation',DEMO_JSONL,'jsonl'),('matrix',MATRIX,'csv')])
def test_canonical_roundtrip(domain,text,format):
    first=convert.convert_table(text,domain,format)
    assert first['manifest']['roundtrip_verified']
    assert first['manifest']['omitted_columns']==[]
    for target in (['jsonl'] if domain=='segmentation' else ['csv','jsonl']):
        second=convert.convert_table(first['text'],domain,'jsonl',target)
        third=convert.convert_table(second['text'],domain,target)
        assert third['text']==first['text']


def test_wide_mapping_exact_decimals_and_explicit_omissions():
    result=convert.convert_table(EXAMPLE,'scores',mapping=EXAMPLE_MAPPING)
    assert result['manifest']['n_records']==6
    source='sample_id,score_a,score_b,metric,unit,direction,notes\n你好,9007199254740993.00000000000000001,0,m,n,higher,private\n'
    with pytest.raises(ValueError,match='omitted'):
        convert.convert_table(source,'scores')
    result=convert.convert_table(source,'scores',allow_extra=True)
    assert json.loads(result['text'])['score_a']=='9007199254740993.00000000000000001'
    assert result['manifest']['omitted_columns']==['notes']
    assert 'private' not in json.dumps(result['manifest'])
    uneven=result['text']+result['text'].replace('你好','other').replace('"metric": "m"','"metric": "second"')
    with pytest.raises(ValueError,match='same sample IDs'):
        convert.convert_table(uneven,'scores','jsonl')


@pytest.mark.parametrize('kwargs', [dict(domain='other'),dict(domain='segmentation'),
    dict(domain='matrix',mapping={}),dict(mapping={}),dict(output_format='xml'),dict(allow_extra='false')])
def test_ambiguous_conversion_rejected(kwargs):
    with pytest.raises(ValueError):
        convert.convert_table(DEMO_CSV,**kwargs)


def test_segmentation_output_and_professional_scope():
    with pytest.raises(ValueError,match='requires JSONL'):
        convert.convert_table(DEMO_JSONL,'segmentation','jsonl','csv')
    with pytest.raises(ValueError):
        convert.convert_table(SCORES,'scores',edition='professional')


def test_no_commit_on_size_or_roundtrip_failure(monkeypatch):
    monkeypatch.setattr(convert,'MAX_BYTES',1)
    with pytest.raises(ValueError,match='exceeds'):
        convert.convert_table(DEMO_CSV)
    monkeypatch.setattr(convert,'MAX_BYTES',4*1024*1024)
    original=convert._load
    def changed(text,domain,format,mapping,edition):
        rows=original(text,domain,format,mapping,edition)
        if format=='jsonl':
            rows[0]['gold']='changed'
        return rows
    monkeypatch.setattr(convert,'_load',changed)
    with pytest.raises(ValueError,match='roundtrip mismatch'):
        convert.convert_table(DEMO_CSV)


def test_save_conversion_and_cli_source_protection(tmp_path,capsys,monkeypatch):
    source=tmp_path/'输入.csv'
    source.write_text(DEMO_CSV,encoding='utf-8')
    result=convert.convert_table(DEMO_CSV)
    for destination in (source,tmp_path/'输入.csv.manifest.json'):
        # The second target's sidecar can itself be the source.
        protected=source if destination==source else tmp_path/'输入.csv.manifest.json.manifest.json'
        with pytest.raises(ValueError,match='source file'):
            convert.save_conversion(result,protected,destination,True)
    output=tmp_path/'规范.jsonl'
    args=['convert',str(source),'--domain','text','--output',str(output)]
    assert cli.main(args)==0
    assert 'roundtrip' in capsys.readouterr().out
    assert output.read_text(encoding='utf-8')==result['text']
    assert cli.main(args)==2
    assert cli.main(args+['--overwrite'])==0
    monkeypatch.setattr(cli,'MAX_BYTES',1)
    assert cli.main(args)==2


def test_cli_wide_mapping_and_jsonl_inference(tmp_path):
    source=tmp_path/'wide.csv'; source.write_text(EXAMPLE,encoding='utf-8')
    mapping=tmp_path/'mapping.json'; mapping.write_text(json.dumps(EXAMPLE_MAPPING),encoding='utf-8')
    output=tmp_path/'paired.jsonl'
    assert cli.main(['convert',str(source),'--domain','scores','--mapping',str(mapping),'--output',str(output)])==0
    assert cli.main(['convert',str(output),'--domain','scores','--to','csv','--output',str(tmp_path/'out.csv')])==0


@pytest.mark.parametrize('failure',['fsync','replace'])
def test_atomic_write_preserves_previous_file_on_failure(tmp_path,monkeypatch,failure):
    path=tmp_path/'report.txt'; storage.write_text_atomic(path,'原始')
    def fail(*args):
        raise OSError('simulated disk failure')
    monkeypatch.setattr(os,failure,fail)
    with pytest.raises(OSError,match='disk failure'):
        storage.write_text_atomic(path,'new')
    assert path.read_text(encoding='utf-8')=='原始'
    assert list(tmp_path.iterdir())==[path]


def test_atomic_file_open_failure_is_clean(tmp_path,monkeypatch):
    def fail(**kwargs):
        raise OSError('cannot stage')
    monkeypatch.setattr(storage.tempfile,'NamedTemporaryFile',fail)
    with pytest.raises(OSError,match='stage'):
        storage.write_text_atomic(tmp_path/'file','value')


def test_conversion_http_returns_validated_download(server):
    status,_,body=request(server,'/api/convert',{'text':EXAMPLE,'domain':'scores','mapping':EXAMPLE_MAPPING})
    value=json.loads(body)
    assert status==200 and value['manifest']['roundtrip_verified']
    assert value['manifest']['n_samples']==3
