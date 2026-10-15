@echo off
rem Builds Pomobar for Windows.
rem   build.bat            -> version 2.0.0
rem   build.bat 2.1.0      -> custom version
rem Output (in dist\):
rem   Pomobar\Pomobar.exe                 the app
rem   Pomobar-<ver>-portable.zip          zip of the app, no install needed
rem   Pomobar-Setup-<ver>.exe             installer (only if Inno Setup 6 is installed)

setlocal
cd /d "%~dp0"

set "VERSION=2.0.0"
if not "%~1"=="" set "VERSION=%~1"

where py >nul 2>&1 && (set "PY=py -3") || (set "PY=python")

if not exist .venv\Scripts\python.exe (
    echo [1/4] Creating virtual environment...
    %PY% -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error

echo [2/4] Installing dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto :error

echo [3/4] Building Pomobar.exe...
pyinstaller --noconfirm --clean --windowed --name Pomobar ^
    --icon packaging\pomobar.ico pomoBar_v2.py || goto :error

powershell -NoProfile -Command "Compress-Archive -Path 'dist\Pomobar\*' -DestinationPath 'dist\Pomobar-%VERSION%-portable.zip' -Force" || goto :error

echo [4/4] Building installer...
set "ISCC="
where iscc >nul 2>&1 && set "ISCC=iscc"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"

if defined ISCC (
    "%ISCC%" /Q /DAppVersion=%VERSION% packaging\Pomobar.iss || goto :error
) else (
    echo Inno Setup 6 not found - skipping the installer.
    echo Install it from https://jrsoftware.org/isdl.php and run build.bat again.
)

echo.
echo Done! Files are in the dist folder:
dir /b dist
exit /b 0

:error
echo.
echo Build failed - see the messages above.
exit /b 1
