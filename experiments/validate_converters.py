# SPDX-License-Identifier: MIT
"""Optional NumPy conversion acceptance gate using disposable synthetic files."""
from hashlib import sha256
import io
import json
from pathlib import Path
import platform
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from examples import prepare_segmentation_npz as converter
from robustband import __version__
from robustband.storage import write_json_atomic
from robustband.domains import audit_domain, verify_audit


def run():
    checked=[]
    with tempfile.TemporaryDirectory(prefix='robustband-converter-') as location:
        root=Path(location); a=root/'a'; b=root/'b'; a.mkdir(); b.mkdir()
        output=root/'paired.jsonl'
        def save(gt,pred=None,pred_b=None):
            np.savez_compressed(a/'组_01_cache.npz',gt=gt,pred=gt if pred is None else pred)
            np.savez_compressed(b/'组_01_cache.npz',gt=gt,pred=gt if pred_b is None else pred_b)
        def reject(label,fn):
            before={p:p.read_bytes() for p in (output,output.with_suffix('.sources.json')) if p.exists()}
            try: fn()
            except (ValueError,OSError,EOFError,zipfile.BadZipFile): pass
            else: raise AssertionError('Expected rejection: '+label)
            assert all(p.read_bytes()==data for p,data in before.items()),label
            checked.append(label)
        def convert(**kwargs):
            return converter.prepare(a,b,output,2,overwrite=True,**kwargs)
        for classes in (2,8,64):
            gt=(np.arange(35).reshape(5,7)%classes).astype('uint8')
            pred=((gt.astype('int64')+1)%classes).astype('int16')
            save(gt,gt,pred)
            manifest=converter.prepare(a,b,output,classes,group_separator='_',id_suffix='_cache',overwrite=True)
            row=json.loads(output.read_text(encoding='utf-8'))
            expected=[[0]*classes for _ in range(classes)]
            for g,p in zip(gt.flat,pred.flat): expected[int(g)][int(p)]+=1
            assert row['confusion_b']==expected and row['sample_id']=='组_01' and row['group']=='组'
            report=audit_domain('segmentation',output.read_text(encoding='utf-8'),'jsonl')
            assert verify_audit(report) and manifest['roundtrip_verified']
            assert all('path' not in s for s in manifest['sources'])
            prior=output.read_bytes()
            converter.prepare(a,b,output,classes,group_separator='_',id_suffix='_cache',overwrite=True)
            assert output.read_bytes()==prior
            checked.append('exact counts, deterministic export and audit replay: %d classes'%classes)
        save(np.array([[0,1,255]],dtype='uint16'),np.array([[0,0,999]],dtype='uint16'))
        manifest=convert(ignore_index=255)
        assert manifest['sources'][0]['active_pixels']==2 and manifest['sources'][0]['ignored_pixels']==1
        checked.append('explicit void mask excludes predictions only at ignored reference pixels')
        reject('undeclared void label',lambda:convert())
        reject('ignore label overlaps class',lambda:convert(ignore_index=1))
        save(np.full((2,3),255,dtype='uint8'))
        reject('all pixels ignored',lambda:convert(ignore_index=255))
        for label,gt,pred in [('floating labels',np.zeros((2,3)),None),
            ('negative prediction',np.zeros((2,3),dtype='int16'),np.full((2,3),-1,dtype='int16')),
            ('shape mismatch',np.zeros((2,3),dtype='uint8'),np.zeros((3,2),dtype='uint8')),
            ('object pickle forbidden',np.zeros((2,3),dtype=object),None),
            ('empty array',np.zeros((0,3),dtype='uint8'),None)]:
            save(gt,pred); reject(label,lambda:convert())
        save(np.zeros((2,3),dtype='uint8'))
        np.savez(b/'组_01_cache.npz',gt=np.ones((2,3),dtype='uint8'),pred=np.zeros((2,3),dtype='uint8'))
        reject('reference array mismatch',lambda:convert())
        save(np.zeros((2,3),dtype='uint8'))
        reject('source overwrite protection',lambda:converter.prepare(a,b,a/'组_01_cache.npz',2,overwrite=True))
        reject('existing output protection',lambda:converter.prepare(a,b,output,2))
        reject('declared suffix mismatch',lambda:convert(id_suffix='missing'))
        reject('class names mismatch',lambda:convert(class_names=['one']))
        reject('empty group separator',lambda:convert(group_separator=''))
        reject('class count budget',lambda:converter.prepare(a,b,output,65,overwrite=True))
        old=converter.MAX_PIXELS; converter.MAX_PIXELS=2
        reject('pixel budget before allocation',lambda:convert()); converter.MAX_PIXELS=old
        old=converter.MAX_EXPANDED_BYTES; converter.MAX_EXPANDED_BYTES=1
        reject('expanded archive budget',lambda:convert()); converter.MAX_EXPANDED_BYTES=old
        old=converter.MAX_BYTES; converter.MAX_BYTES=1
        reject('reloadable output budget',lambda:convert()); converter.MAX_BYTES=old
        old=converter.MAX_ROWS; converter.MAX_ROWS=0
        reject('record budget',lambda:convert()); converter.MAX_ROWS=old
        with zipfile.ZipFile(a/'组_01_cache.npz','w') as archive:
            stream=io.BytesIO()
            np.lib.format.write_array_header_1_0(stream,{'descr':'|u1','fortran_order':False,'shape':(2**31,2**31)})
            archive.writestr('gt.npy',stream.getvalue()); archive.writestr('pred.npy',stream.getvalue())
        reject('declared array shape bomb',lambda:convert())
        (a/'组_01_cache.npz').write_bytes(b'not a zip file')
        reject('malformed archive',lambda:convert())
        (b/'组_01_cache.npz').unlink()
        reject('sample ID mismatch',lambda:convert())
    result={'schema':'robustband.converter_acceptance/v1','version':__version__,'python':platform.python_version(),
        'numpy':np.__version__,'checks':checked,'passed':len(checked),
        'source_sha256_lf':{str(p.relative_to(ROOT)).replace('\\','/'):sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
             for p in (Path(__file__),ROOT/'examples/prepare_segmentation_npz.py')},
        'scope':'Synthetic converter acceptance checks; source arrays are disposable and no external dataset is published.'}
    target=ROOT/'results'/('converter_acceptance_%s.json'%__version__)
    write_json_atomic(target, result)
    print('PASS: %d converter checks'%len(checked))


if __name__=='__main__': run()
