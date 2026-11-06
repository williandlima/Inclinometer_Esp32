@echo off
REM ======================================================================
REM  Cria o icone "Inclinometro 2 Eixos (Avibras Aeroco)" na Area de
REM  Trabalho e no Menu Iniciar abrindo o app DIRETO DO CODIGO-FONTE desta
REM  pasta (sem VSCode, sem janela preta, sem .exe - nao e bloqueado pelo
REM  Controle Inteligente de Aplicativos do Windows).
REM
REM  O que ele faz:
REM   1) atualiza o codigo (git pull), se a pasta veio do git clone;
REM   2) acha o Python (python-app\.venv, PATH ou launcher "py");
REM   3) instala as bibliotecas que faltarem (so na primeira vez);
REM   4) cria os atalhos e REMOVE os atalhos antigos que abriam o .exe
REM      instalado (versao antiga) - era por isso que o icone continuava
REM      abrindo a versao velha;
REM   5) mostra a versao e abre o programa.
REM  Depois disso, para atualizar basta rodar este arquivo de novo.
REM ======================================================================

setlocal EnableExtensions
title Atalho - Inclinometro 2 Eixos (codigo-fonte)
cd /d "%~dp0.."
set "APPDIR=%CD%"
for %%R in ("%APPDIR%\..") do set "REPO=%%~fR"
set "LNKNAME=Inclinometro 2 Eixos (Avibras Aeroco)"
set "TMPF=%TEMP%\inclinometro_atalho.txt"

echo.
echo === Inclinometro 2 Eixos - icone para o codigo-fonte ===
echo Pasta do codigo: %APPDIR%
echo.

REM ---- 1) Atualiza o codigo ---------------------------------------------
if not exist "%REPO%\.git" goto :sem_git
where git >nul 2>nul
if errorlevel 1 goto :sem_git
echo Atualizando o codigo - git pull...
git -C "%REPO%" pull --ff-only
if errorlevel 1 echo [AVISO] git pull falhou. Seguindo com o codigo que ja esta na pasta.
echo.
goto :python
:sem_git
echo [AVISO] Pasta sem git ^(baixada como .zip^): o codigo NAO sera atualizado.
echo         Para atualizar sozinho, use "git clone" ^(ver INSTALACAO_WINDOWS.md^).
echo.

REM ---- 2) Acha o Python -------------------------------------------------
:python
set "PYC="
set "PYW="
if exist "%APPDIR%\.venv\Scripts\python.exe" set "PYC=%APPDIR%\.venv\Scripts\python.exe"
if defined PYC goto :achou_python
REM Pergunta ao proprio Python onde ele esta. Funciona tambem com o Python
REM da Microsoft Store (pasta WindowsApps). Se nao houver Python, o
REM "python" do Windows e so um atalho para a Store e devolve erro aqui.
python -c "import sys; print(sys.executable)" > "%TMPF%" 2>nul
if not errorlevel 1 set /p PYC=<"%TMPF%"
if defined PYC goto :achou_python
py -3 -c "import sys; print(sys.executable)" > "%TMPF%" 2>nul
if not errorlevel 1 set /p PYC=<"%TMPF%"
if defined PYC goto :achou_python
echo [ERRO] Python nao encontrado.
echo Instale o Python 3.11 em python.org ^(marque "Add python.exe to PATH"^)
echo e rode este arquivo de novo.
goto :fim_erro

:achou_python
for %%D in ("%PYC%") do if exist "%%~dpDpythonw.exe" set "PYW=%%~dpDpythonw.exe"
if not defined PYW for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do if not defined PYW set "PYW=%%P"
if not defined PYW (
    echo [AVISO] pythonw.exe nao encontrado: o app vai abrir com uma janela de terminal junto.
    set "PYW=%PYC%"
)
echo Python: %PYC%

REM ---- 3) Bibliotecas ---------------------------------------------------
set "IMPORTS=import PyQt5, bleak, serial, pymodbus, reportlab, matplotlib, numpy"
"%PYC%" -c "%IMPORTS%" >nul 2>nul
if not errorlevel 1 goto :libs_ok
echo.
echo Instalando as bibliotecas do app - so na primeira vez, 1 a 3 minutos...
"%PYC%" -m pip install -r "%APPDIR%\requirements.txt"
"%PYC%" -c "%IMPORTS%" >nul 2>nul
if not errorlevel 1 goto :libs_ok
echo Tentando de novo so para este usuario...
"%PYC%" -m pip install --user -r "%APPDIR%\requirements.txt"
"%PYC%" -c "%IMPORTS%" >nul 2>nul
if not errorlevel 1 goto :libs_ok
echo [ERRO] Nao foi possivel instalar as bibliotecas ^(sem internet ou proxy da empresa?^).
echo Rode no terminal: "%PYC%" -m pip install -r "%APPDIR%\requirements.txt"
goto :fim_erro
:libs_ok

REM ---- Versao que o icone vai abrir -------------------------------------
set "VER=?"
"%PYC%" -c "import sys; sys.path.insert(0, sys.argv[1]); import app_version; print(app_version.APP_VERSION)" "%APPDIR%" > "%TMPF%" 2>nul
if not errorlevel 1 set /p VER=<"%TMPF%"
del "%TMPF%" >nul 2>nul

REM ---- 4) Atalhos (novos) e limpeza dos antigos -------------------------
set "TARGET=%PYW%"
set "TARGS="%APPDIR%\main.py""
set "WDIR=%APPDIR%"
set "ICON=%APPDIR%\assets\logo.ico"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$w=New-Object -ComObject WScript.Shell; $keep=@();" ^
  "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {" ^
  "  $p=Join-Path $d ($env:LNKNAME + '.lnk'); $s=$w.CreateShortcut($p);" ^
  "  $s.TargetPath=$env:TARGET; $s.Arguments=[string]$env:TARGS; $s.WorkingDirectory=$env:WDIR; $s.IconLocation=$env:ICON;" ^
  "  $s.Description='Pan-tilt meter - Inclinometro Avibras Aeroco'; $s.Save(); $keep+=$p }" ^
  "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('CommonDesktopDirectory'), [Environment]::GetFolderPath('CommonPrograms'))) {" ^
  "  if (-not $d -or -not (Test-Path -LiteralPath $d)) { continue }" ^
  "  Get-ChildItem -LiteralPath $d -Filter 'Inclinometro*.lnk' -Recurse -Depth 1 -ErrorAction SilentlyContinue | ForEach-Object {" ^
  "    if ($keep -contains $_.FullName) { return }" ^
  "    $t=$w.CreateShortcut($_.FullName).TargetPath;" ^
  "    if ($t -like '*\Inclinometro2Eixos.exe' -and $t -ne $env:TARGET) {" ^
  "      try { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop; Write-Host ('Atalho antigo removido: ' + $_.FullName) }" ^
  "      catch { Write-Host ('[AVISO] Atalho da versao antiga que nao pude apagar: ' + $_.FullName); Write-Host '        Desinstale a versao antiga em Configuracoes > Aplicativos, ou apague esse atalho.' } } } }"
if errorlevel 1 (
    echo [ERRO] Nao foi possivel criar o atalho.
    goto :fim_erro
)

REM ---- 5) Pronto --------------------------------------------------------
echo.
echo OK: icone "%LNKNAME%" na Area de Trabalho e no Menu Iniciar.
echo Versao do app: %VER%   ^(aparece no topo da tela: "App v%VER%"^)
echo Para atualizar no futuro, rode este arquivo de novo.
echo.
echo Abrindo o programa...
start "" "%PYW%" "%APPDIR%\main.py"
pause
exit /b 0

:fim_erro
echo.
pause
exit /b 1
