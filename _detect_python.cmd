@rem SPDX-License-Identifier: MIT
@echo off
rem Locate a usable Python interpreter for the double-click launchers.
rem Call this file, do not run it on its own:  call "%~dp0_detect_python.cmd"
rem
rem Success: sets ROBUSTBAND_PY to a command prefix that stays valid when it is
rem          expanded unquoted, for example  py -3  or  "C:\Program Files\...".
rem Failure: explains the problem, waits for a key press, exits with code 1.
rem
rem Order of preference: ROBUSTBAND_PYTHON, a project .venv, `python` on PATH,
rem the `py` launcher, then the default per-user and machine install folders.
rem A candidate is accepted only if it runs and reports Python 3.9 or newer.
rem That check rejects the Microsoft Store placeholder `python.exe`, which
rem exits with code 9009 and prints nothing, so a bare `python` is not trusted
rem on its own. Probes use `call` so a .bat shim returns control.

setlocal EnableExtensions
set "ROBUSTBAND_PY="
set "TOO_OLD="
set "PROBE="
set "CAND="

rem 1. Explicit override, for an interpreter installed somewhere unusual.
if defined ROBUSTBAND_PYTHON (
    call :accept "%ROBUSTBAND_PYTHON%"
    if defined ROBUSTBAND_PY goto :found
)

rem 2. A virtual environment kept inside the source folder.
if exist "%~dp0.venv\Scripts\python.exe" (
    call :accept "%~dp0.venv\Scripts\python.exe"
    if defined ROBUSTBAND_PY goto :found
)

rem 3. `python` on PATH: real installs, conda shells, activated envs.
where python >nul 2>&1
if not errorlevel 1 (
    call :accept "python"
    if defined ROBUSTBAND_PY goto :found
)

rem 4. The official Windows launcher picks the newest Python 3 it knows about.
where py >nul 2>&1
if not errorlevel 1 (
    call :accept "py -3"
    if defined ROBUSTBAND_PY goto :found
)

rem 5. Default python.org install folders, newest major-minor first.
for /f "delims=" %%D in ('dir /ad /b /o-n "%LOCALAPPDATA%\Programs\Python\Python3*" 2^>nul') do (
    call :accept "%LOCALAPPDATA%\Programs\Python\%%D\python.exe"
    if defined ROBUSTBAND_PY goto :found
)
for /f "delims=" %%D in ('dir /ad /b /o-n "%ProgramFiles%\Python3*" 2^>nul') do (
    call :accept "%ProgramFiles%\%%D\python.exe"
    if defined ROBUSTBAND_PY goto :found
)

goto :fail

:found
echo [robustband] Python: %PROBE%
endlocal & set "ROBUSTBAND_PY=%ROBUSTBAND_PY%"
exit /b 0

:fail
echo.
echo [robustband] No usable Python 3.9 or newer interpreter was found.
if defined TOO_OLD echo [robustband] An older Python is installed; this tool needs 3.9 or newer.
echo.
echo [robustband] Install Python 3.9+ from
echo              https://www.python.org/downloads/windows/
echo              The installer also provides the "py" launcher.
echo [robustband] To pick a specific interpreter, set the full path first:
echo              set ROBUSTBAND_PYTHON=C:\path\to\python.exe
echo.
echo [robustband] The WELCOME.html preview works without Python.
echo.
pause
endlocal & exit /b 1

:accept
rem %~1 is a command prefix (python, py -3) or a full path to python.exe.
set "CAND=%~1"
if not defined CAND exit /b 1
if exist "%CAND%" (
    set "PROBE="%CAND%""
) else (
    set "PROBE=%CAND%"
)
call %PROBE% -c "import sys" >nul 2>&1
if errorlevel 1 exit /b 1
call %PROBE% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 3)" >nul 2>&1
if not errorlevel 1 set "ROBUSTBAND_PY=%PROBE%"
if errorlevel 1 set "TOO_OLD=1"
exit /b 0
