# SPDX-License-Identifier: MIT
"""Convert paired integer pred/gt NPZ caches to validated confusion JSONL.

NumPy is an optional preprocessing dependency. No models or checkpoints are loaded.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robustband.convert import convert_table
from robustband.input_utils import MAX_BYTES, MAX_ROWS
from robustband.storage import write_text_atomic

MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_PIXELS = 16 * 1024 * 1024


def _load(path, np):
    """Check archive and array allocation budgets before NumPy materializes data."""
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if sum(m.file_size for m in members) > MAX_EXPANDED_BYTES:
            raise ValueError('NPZ expanded data exceeds 256 MiB: '+path.name)
        for key in ('gt.npy', 'pred.npy'):
            matches = [m for m in members if m.filename == key]
            if len(matches) != 1:
                raise ValueError('NPZ needs exactly one '+key+': '+path.name)
            with archive.open(matches[0]) as stream:
                version = np.lib.format.read_magic(stream)
                if version == (1, 0):
                    shape, _, dtype = np.lib.format.read_array_header_1_0(stream)
                elif version == (2, 0):
                    shape, _, dtype = np.lib.format.read_array_header_2_0(stream)
                else:
                    raise ValueError('Unsupported NPY header version: '+str(version))
                if len(shape) != 2 or dtype.kind not in 'ui' or dtype.hasobject:
                    raise ValueError('NPZ labels must be two-dimensional integer arrays: '+path.name)
                pixels = int(shape[0]) * int(shape[1])
                if not 0 < pixels <= MAX_PIXELS or pixels * dtype.itemsize > MAX_EXPANDED_BYTES:
                    raise ValueError('NPZ pixel/allocation budget exceeded: '+path.name)
    with np.load(path, allow_pickle=False) as archive:
        return archive['gt'], archive['pred']


def prepare(folder_a, folder_b, output, n_classes, class_names=None, group_separator=None,
            id_suffix='', ignore_index=None, overwrite=False):
    """Strictly pair IDs and labels, validate a reloadable result, then save it."""
    import numpy as np
    if not 2 <= n_classes <= 64:
        raise ValueError('n-classes must be between 2 and 64')
    if group_separator == '':
        raise ValueError('group-separator must be nonempty when provided')
    names = class_names or [str(k) for k in range(n_classes)]
    if len(names) != n_classes or len(set(names)) != len(names) or any(not n.strip() for n in names):
        raise ValueError('Provide one distinct nonempty class name for each integer label')
    if ignore_index is not None and 0 <= ignore_index < n_classes:
        raise ValueError('ignore-index must be outside the declared class labels')
    indexed = []
    for folder in (folder_a, folder_b):
        files = {}
        for path in Path(folder).glob('*.npz'):
            if id_suffix and not path.stem.endswith(id_suffix):
                raise ValueError('Every basename must end with the declared id-suffix: '+path.name)
            identity = path.stem[:-len(id_suffix)] if id_suffix else path.stem
            if not identity or identity in files:
                raise ValueError('Empty or duplicate sample ID after applying filename rule')
            files[identity] = path
        indexed.append(files)
    if not indexed[0] or set(indexed[0]) != set(indexed[1]):
        raise ValueError('The folders need exactly the same nonempty sample-ID set; no intersection or truncation')
    if len(indexed[0]) > MAX_ROWS:
        raise ValueError('Use at most 5000 records; split the input folders')
    output = Path(output)
    sidecar = output.with_suffix('.sources.json')
    sources_resolved = {p.resolve() for files in indexed for p in files.values()}
    if output.resolve() == sidecar.resolve() or sources_resolved.intersection((output.resolve(), sidecar.resolve())):
        raise ValueError('Output paths cannot overwrite a source archive or each other')
    if not overwrite and any(p.exists() for p in (output, sidecar)):
        raise ValueError('Output exists; choose another path or explicitly use --overwrite')
    records, sources = [], []
    for identity in sorted(indexed[0]):
        row = {'sample_id': identity, 'group': identity.split(group_separator)[0] if group_separator else '',
               'class_names': names}
        reference = None
        for key, files in zip(('confusion_a', 'confusion_b'), indexed):
            path = files[identity]
            gt, pred = _load(path, np)
            if gt.shape != pred.shape:
                raise ValueError('Shape mismatch for '+identity)
            if reference is not None and not np.array_equal(reference, gt):
                raise ValueError('Ground-truth arrays differ for '+identity)
            reference = gt
            active = gt != ignore_index if ignore_index is not None else np.ones(gt.shape, dtype=bool)
            labels, predictions = gt[active], pred[active]
            if (labels.size == 0 or int(labels.min()) < 0 or int(predictions.min()) < 0
                    or int(labels.max()) >= n_classes or int(predictions.max()) >= n_classes):
                raise ValueError('Empty active mask or label range mismatch for '+identity)
            code = labels.astype('int64') * n_classes + predictions.astype('int64')
            row[key] = np.bincount(code.ravel(), minlength=n_classes**2).reshape(n_classes, n_classes).tolist()
            sources.append({'sample_id':identity,'side':key,'filename':path.name,
                'sha256':sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,
                'shape':list(gt.shape),'gt_dtype':str(gt.dtype),'pred_dtype':str(pred.dtype),
                'active_pixels':int(labels.size),'ignored_pixels':int(gt.size-labels.size),
                'ground_truth_sha256':sha256(gt.tobytes()).hexdigest()})
        records.append(row)
    text = ''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records)
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Output exceeds 4 MiB; split the input folders')
    converted = convert_table(text, 'segmentation', 'jsonl', 'jsonl')
    manifest = {'schema':'robustband.npz_preparation/v2','n_records':len(records),'class_names':names,
        'group_rule':group_separator,'id_suffix':id_suffix,'ignore_index':ignore_index,
        'ground_truth_arrays_equal':True,'numpy_version':np.__version__,
        'output_sha256':sha256(text.encode('utf-8')).hexdigest(),'sources':sources,
        'roundtrip_verified':converted['manifest']['roundtrip_verified'],
        'converter_sha256_lf':sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
        'scope':'Stored integer labels at stored resolution; no inference, training or annotation verification. Void pixels require an explicit ignore-index. Source paths are omitted.'}
    write_text_atomic(sidecar, json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    write_text_atomic(output, text)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder_a', type=Path)
    parser.add_argument('folder_b', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--n-classes', type=int, required=True)
    parser.add_argument('--class-names', help='Comma-separated names in integer label order')
    parser.add_argument('--group-separator', help='Use basename prefix before this separator as group')
    parser.add_argument('--id-suffix', default='')
    parser.add_argument('--ignore-index', type=int, help='Explicit void label outside 0..n-classes-1')
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args(argv)
    try:
        manifest = prepare(args.folder_a, args.folder_b, args.output, args.n_classes,
            args.class_names.split(',') if args.class_names else None, args.group_separator,
            args.id_suffix, args.ignore_index, args.overwrite)
    except (ValueError, OSError, EOFError, zipfile.BadZipFile) as exc:
        print('Error: '+str(exc), file=sys.stderr)
        return 2
    print('Prepared %d strictly paired records (roundtrip verified): %s' % (manifest['n_records'], args.output))
    return 0


if __name__ == '__main__':
    sys.exit(main())
