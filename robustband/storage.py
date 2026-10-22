# SPDX-License-Identifier: MIT
"""Stage UTF-8 artifacts and replace individual files without truncating them."""
import os
import json
from pathlib import Path
import tempfile


def write_text_atomic(path, text):
    """On a staging failure, preserve the previous file and remove the temporary."""
    path = Path(path)
    data = text.encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.'+path.name+'.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return path


def write_json_atomic(path, value):
    """Write UTF-8 JSON with LF line endings and reject nonstandard numbers."""
    return write_text_atomic(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
