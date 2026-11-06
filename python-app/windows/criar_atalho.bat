@echo off
REM Cria na Area de Trabalho um atalho com a logo para abrir o Inclinometro
REM direto do codigo-fonte, sem VSCode e sem janela preta de terminal.
REM Usa o ambiente virtual de windows\install.bat (python-app\.venv) se ele
REM existir; senao, o Python do PATH (o mesmo que o VSCode usa).
REM Para distribuir para operadores, prefira o instalador Setup.exe
REM (ver INSTALACAO_WINDOWS.md).

setlocal
cd /d "%~dp0.."
set "APPDIR=%CD%"

set "PYW="
if exist "%APPDIR%\.venv\Scripts\pythonw.exe" set "PYW=%APPDIR%\.venv\Scripts\pythonw.exe"
if not defined PYW (
    for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do if not defined PYW set "PYW=%%P"
)
if not defined PYW (
    echo [ERRO] Python nao encontrado. Rode primeiro windows\install.bat.
    pause
    exit /b 1
)

REM pythonw.exe fica ao lado de python.exe: testa as bibliotecas com ele.
set "PYC=%PYW:pythonw.exe=python.exe%"
"%PYC%" -c "import PyQt5, bleak, serial, pymodbus, reportlab, matplotlib" >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Faltam bibliotecas no Python "%PYC%".
    echo Rode windows\install.bat e depois este arquivo de novo.
    pause
    exit /b 1
)

set "LNKNAME=Inclinometro 2 Eixos (Avibras Aeroco)"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d ($env:LNKNAME + '.lnk')));" ^
  "$s.TargetPath=$env:PYW;" ^
  "$s.Arguments='\"' + (Join-Path $env:APPDIR 'main.py') + '\"';" ^
  "$s.WorkingDirectory=$env:APPDIR;" ^
  "$s.IconLocation=(Join-Path $env:APPDIR 'assets\logo.ico');" ^
  "$s.Description='Pan-tilt meter - Inclinometro Avibras Aeroco';" ^
  "$s.Save()"
if errorlevel 1 (
    echo [ERRO] Nao foi possivel criar o atalho.
    pause
    exit /b 1
)

echo.
echo Atalho "%LNKNAME%" criado na Area de Trabalho.
echo De duplo clique nele para abrir o software.
pause
