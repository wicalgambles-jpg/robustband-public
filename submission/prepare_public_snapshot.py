# SPDX-License-Identifier: MIT
"""Copy reviewed source files into a new folder without development Git history."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={
    'docs/math_dl_transfer.md',
    'results/review_dual_development_2026-10-12.json',
    'results/review_dual_held_out_2026-10-12.json',
    'results/converter_acceptance_0.9.0.json',
}


def allowed(name):
    if name in EXCLUDED: return False
    if name.startswith(('results/manuscript_build_','results/submission_bundle_')): return False
    if name.startswith('results/quality_gate_') and not name.endswith(('_0.9.0.json','_1.0.0.json')): return False
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args(); output=args.output.resolve()
    if output.exists(): raise SystemExit('Choose a new empty snapshot path.')
    names=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode('utf-8').split('\0')
    files=sorted({name for name in names if name and allowed(name)})
    secret=re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----')
    private_path=re.compile(r'[A-Z]:[\\/]+(?:Code|Users)[\\/]+')
    findings=[]
    for name in files:
        path=ROOT/name
        if not path.is_file(): continue
        data=path.read_bytes()
        if secret.search(data): findings.append((name,'credential pattern'))
        text=data.decode('utf-8','replace')
        if name.startswith('results/') and private_path.search(text): findings.append((name,'private absolute path'))
    if findings: raise SystemExit('Review blocked files: '+str(findings))
    output.mkdir(parents=True)
    identities={}
    for name in files:
        source=ROOT/name
        if source.is_file():
            target=output/name; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target); identities[name]=sha256(target.read_bytes()).hexdigest()
    receipt={'schema':'robustband.public_snapshot/v1','version':'1.0.0','files':len(identities),
        'git_history_copied':False,'credential_patterns_found':0,'private_result_paths_found':0,
        'excluded_categories':['internal preparation artifacts','private research-note identities','earlier internal quality receipts','interim post-baseline receipts'],
        'file_sha256':identities,'scope':'File inventory and pattern scan; public projections retain numerical evidence with their derivation stated.'}
    (ROOT/'build/public_snapshot_inventory.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print('Prepared %d files in a new folder; no Git history copied.'%len(identities))


if __name__=='__main__': main()
