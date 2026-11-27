@echo off
title Text to Speech Web Studio
cd /d "%~dp0"
echo =====================================================================
echo  Launching Text to Speech Studio (Web Edition) ...
echo =====================================================================

REM Detect virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Find Python
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PY=python
) else (
    where py >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set PY=py -3
    ) else (
        echo [ERROR] Python not found. Install Python 3.10+ from python.org
        pause
        exit /b 1
    )
)

REM Auto-install dependencies if needed
%PY% -c "import edge_tts, numpy, imageio_ffmpeg" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installing dependencies...
    %PY% -m pip install -r requirements.txt
)

%PY% web_studio.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Web Studio failed to launch.
    echo     %PY% -m pip install -r requirements.txt
    echo.
    pause
)
