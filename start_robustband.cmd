@rem SPDX-License-Identifier: MIT
@echo off
cd /d "%~dp0"
if not exist "%~dp0_detect_python.cmd" (
    echo [robustband] _detect_python.cmd is missing next to this launcher.
    echo [robustband] Re-extract the whole source bundle, or run:
    echo              python -m robustband ui
    pause
    exit /b 1
)
call "%~dp0_detect_python.cmd"
if errorlevel 1 exit /b 1
call %ROBUSTBAND_PY% -m robustband ui
if errorlevel 1 pause
