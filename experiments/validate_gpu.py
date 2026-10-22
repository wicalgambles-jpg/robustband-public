# SPDX-License-Identifier: MIT
"""Optional real CUDA interoperability gate. Requires NumPy and CuPy CUDA wheels.

Core auditing uses exact CPU arithmetic. This gate validates GPU-derived caches,
conversion and audit replay against a separately implemented CPU count reference.
"""
from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import cupy as cp
from examples.prepare_segmentation_npz import prepare
from robustband import __version__
from robustband.domains import audit_domain, verify_audit


def run():
    device=cp.cuda.runtime.getDeviceProperties(cp.cuda.Device().id)
    cases=[]
    with tempfile.TemporaryDirectory(prefix='robustband-cuda-') as location:
        root=Path(location); a=root/'a'; b=root/'b'; a.mkdir(); b.mkdir()
        for classes in (2,8,64):
            shape=(37,53)
            gt=(np.arange(np.prod(shape)).reshape(shape)%classes).astype('int32')
            gt[0,:5]=255
            # CPU builds deterministic logits; actual argmax and counting run on CUDA.
            logits=np.random.default_rng(1701+classes).normal(size=shape+(classes,)).astype('float32')
            gpu_logits=cp.asarray(logits)
            pred_a=cp.argmax(gpu_logits,axis=2).astype(cp.int32)
            pred_b=cp.argmax(-gpu_logits,axis=2).astype(cp.int32)
            gpu_gt=cp.asarray(gt); mask=gpu_gt!=255
            gpu_counts=cp.bincount((gpu_gt[mask]*classes+pred_a[mask]).astype(cp.int64),minlength=classes**2).reshape(classes,classes)
            cp.cuda.Stream.null.synchronize()
            cpu_a=np.argmax(logits,axis=2); cpu_b=np.argmax(-logits,axis=2)
            assert np.array_equal(cp.asnumpy(pred_a),cpu_a) and np.array_equal(cp.asnumpy(pred_b),cpu_b)
            counts_a=[[0]*classes for _ in range(classes)]; counts_b=[[0]*classes for _ in range(classes)]
            for g,pa,pb in zip(gt.flat,cpu_a.flat,cpu_b.flat):
                if g!=255:
                    counts_a[int(g)][int(pa)]+=1; counts_b[int(g)][int(pb)]+=1
            assert cp.asnumpy(gpu_counts).tolist()==counts_a
            np.savez_compressed(a/'sample.npz',gt=cp.asnumpy(gpu_gt),pred=cp.asnumpy(pred_a))
            np.savez_compressed(b/'sample.npz',gt=cp.asnumpy(gpu_gt),pred=cp.asnumpy(pred_b))
            output=root/'paired.jsonl'
            manifest=prepare(a,b,output,classes,ignore_index=255,overwrite=True)
            row=json.loads(output.read_text(encoding='utf-8'))
            assert row['confusion_a']==counts_a and row['confusion_b']==counts_b
            report=audit_domain('segmentation',output.read_text(encoding='utf-8'),'jsonl')
            assert verify_audit(report)
            # Rebuild the audit directly from the CPU loop's counts and compare exact results.
            reference=audit_domain('segmentation',json.dumps(dict(sample_id='sample',confusion_a=counts_a,confusion_b=counts_b,
                class_names=[str(k) for k in range(classes)],group='')),'jsonl')
            assert reference['result']==report['result']
            cases.append({'classes':classes,'shape':list(shape),'ignored_pixels':5,
                'cuda_argmax_equals_cpu':True,'cuda_counts_equals_cpu_loop':True,'converted_counts_equal':True,
                'exact_audit_equals_cpu':True,'replay_verified':True,'roundtrip_verified':manifest['roundtrip_verified'],
                'exact_band':report['result']['exact_band']})
    name=device['name']; name=name.decode() if isinstance(name,bytes) else name
    result={'schema':'robustband.gpu_interoperability/v1','version':__version__,'date':'2026-10-21',
        'python':platform.python_version(),'cupy':cp.__version__,'numpy':np.__version__,'gpu':name,
        'cuda_runtime':cp.cuda.runtime.runtimeGetVersion(),'cuda_driver_api':cp.cuda.runtime.driverGetVersion(),
        'driver':subprocess.check_output(['nvidia-smi','--query-gpu=driver_version','--format=csv,noheader'],text=True).strip(),
        'cases':cases,'passed':len(cases),'device_pool_peak_reserved_bytes':cp.get_default_memory_pool().total_bytes(),
        'source_sha256_lf':{str(p.relative_to(ROOT)).replace('\\','/'):sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
          for p in (Path(__file__),ROOT/'examples/prepare_segmentation_npz.py',ROOT/'robustband/convert.py',ROOT/'robustband/segmentation.py')},
        'scope':'Actual CUDA argmax and bincount on this GPU; synthetic integer caches, conversion and exact CPU audit replay. No training, inference benchmark or universal GPU support claim.'}
    (ROOT/'results'/('gpu_interoperability_%s.json'%__version__)).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('PASS: CUDA argmax/counts, NPZ conversion and exact CPU reference on '+name)


if __name__=='__main__': run()
