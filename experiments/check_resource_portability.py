# SPDX-License-Identifier: MIT
"""Verify the complete committed grid on disposable LF and CRLF source copies."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import resource_grid
from robustband import __version__
from robustband.storage import write_json_atomic


def main():
    expected = json.loads((ROOT/'results'/('resource_grid_%s.json'%__version__)).read_text(encoding='utf-8'))
    manifest_name = 'experiments/resource_sources.json'
    sources = json.loads((ROOT/manifest_name).read_text(encoding='utf-8'))
    names = {manifest_name} | {name for benchmark in sources['benchmarks'] for name in benchmark['files'].values()}
    normalized = {name:(ROOT/name).read_bytes().replace(b'\r\n',b'\n') for name in names}
    cases = []
    original_root = resource_grid.ROOT
    with tempfile.TemporaryDirectory(prefix='robustband-grid-newlines-') as location:
        try:
            for label, ending in (('LF',b'\n'),('CRLF',b'\r\n')):
                root = Path(location)/label
                for name, data in normalized.items():
                    path = root/name
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(data.replace(b'\n',ending))
                resource_grid.ROOT = root
                actual = resource_grid.analyze(root/manifest_name)
                assert actual == expected, label+' grid differs from committed receipt'
                cases.append({'checkout':label,'full_receipt_equal':True,'grid_sha256':actual['grid_sha256'],
                    'physical_bytes':{name:(root/name).stat().st_size for name in sorted(names)}})
        finally:
            resource_grid.ROOT = original_root
    report = {'schema':'robustband.resource_portability/v1','version':__version__,'passed':len(cases),'cases':cases,
        'source_sha256_lf':{str(p.relative_to(ROOT)).replace('\\','/'):sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for p in (Path(__file__),ROOT/'experiments/resource_grid.py',ROOT/'robustband/storage.py')},
        'scope':'Complete grid, provenance and canonical hash compared against the committed receipt using LF and CRLF copies of every declared input; repository inputs are never modified.'}
    write_json_atomic(ROOT/'build'/('resource_portability_%s.json'%__version__),report)
    print('VERIFY PASS: LF and CRLF copies reproduce the complete committed resource grid')


if __name__=='__main__': main()
