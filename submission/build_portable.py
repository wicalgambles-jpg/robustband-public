# SPDX-License-Identifier: MIT
"""Build a Windows standalone folder with the exact core, UI and source identities."""
from hashlib import sha256
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from robustband import __version__
from robustband.storage import write_json_atomic


def main():
    if sys.platform!='win32': raise SystemExit('Build the Windows portable on Windows.')
    name='robustband-%s-windows-x64'%__version__
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--name',name,
        '--paths',str(ROOT),'--distpath',str(ROOT/'dist'),'--workpath',str(ROOT/'build/portable'),
        '--specpath',str(ROOT/'build/portable')]
    # Replay hashes actual source bytes. Include source files alongside frozen modules.
    for path in sorted((ROOT/'robustband').iterdir()):
        if path.suffix in ('.py','.html'):
            command+=['--add-data',str(path)+':robustband']
    for module in ('numpy','cupy','pytest','coverage','setuptools'):
        command+=['--exclude-module',module]
    command.append(str(ROOT/'submission/portable_entry.py'))
    subprocess.run(command,cwd=ROOT,check=True)
    folder=ROOT/'dist'/name
    for filename in ('LICENSE','README.md','SECURITY.md'):
        shutil.copyfile(ROOT/filename,folder/filename)
    licenses=folder/'licenses'; licenses.mkdir(exist_ok=True)
    python_license=Path(sysconfig.get_path('stdlib'))/'LICENSE.txt'
    if not python_license.exists(): python_license=Path(sys.base_prefix)/'LICENSE.txt'
    shutil.copyfile(python_license,licenses/'Python-LICENSE.txt')
    (licenses/'NOTICE.txt').write_text('robustband: MIT (see ../LICENSE). Bundled CPython and its components: see Python-LICENSE.txt. Microsoft runtime files retain their original licenses. PyInstaller bootloader uses the distribution exception: https://pyinstaller.org/en/stable/license.html\n',encoding='utf-8')
    exe=name+'.exe'
    for edition in ('professional','generalized'):
        (folder/('start_'+edition+'.cmd')).write_bytes(('@echo off\r\ncd /d "%~dp0"\r\n"%~dp0'+exe+'" --edition '+edition+' ui\r\nif errorlevel 1 pause\r\n').encode('ascii'))
    (folder/'START-HERE.txt').write_text('robustband '+__version__+'\n\nExtract this entire folder, then double-click start_generalized.cmd or start_professional.cmd. Python installation is not required. Keep _internal beside the executable. Stop the local server using Stop session in the browser or Ctrl+C in its console. The executable is unsigned. For editable adapters and NPZ preprocessing, use the source edition and its optional dependencies.\n\nCLI: '+exe+' --help\n',encoding='utf-8')
    archive=Path(shutil.make_archive(str(ROOT/'dist'/name),'zip',ROOT/'dist',name))
    receipt={'schema':'robustband.portable_build/v1','version':__version__,'platform':platform.platform(),
        'python':platform.python_version(),'format':'PyInstaller onedir','archive':archive.name,
        'sha256':sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,
        'runtime_python_installation_required':False,'optional_numpy_cupy_bundled':False,
        'source_files_included_for_replay':True,'signed':False}
    write_json_atomic(ROOT/'results'/('portable_build_%s.json'%__version__), receipt)
    print('Built '+archive.name)


if __name__=='__main__': main()
