@echo off
REM Vai junto da versao PORTATIL (pasta Inclinometro2Eixos). Rode UMA vez,
REM com a pasta ja no lugar definitivo (ex.: C:\Inclinometro2Eixos):
REM  1) tira o bloqueio "arquivo baixada da internet" de todos os arquivos
REM     da pasta (e' isso que faz o Windows tratar o .exe como perigoso);
REM  2) cria na Area de Trabalho um ATALHO para o .exe.
REM Nunca copie so o Inclinometro2Eixos.exe para a Area de Trabalho: ele
REM precisa da pasta _internal ao lado e nao abre sozinho.

setlocal
cd /d "%~dp0"
if not exist "%CD%\Inclinometro2Eixos.exe" (
    echo [ERRO] Inclinometro2Eixos.exe nao esta nesta pasta.
    pause
    exit /b 1
)
set "APPDIR=%CD%"
set "LNKNAME=Inclinometro 2 Eixos (Avibras Aeroco)"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-ChildItem -LiteralPath $env:APPDIR -Recurse -File | Unblock-File;" ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d ($env:LNKNAME + '.lnk')));" ^
  "$s.TargetPath=(Join-Path $env:APPDIR 'Inclinometro2Eixos.exe');" ^
  "$s.WorkingDirectory=$env:APPDIR;" ^
  "$s.IconLocation=(Join-Path $env:APPDIR 'Inclinometro2Eixos.exe') + ',0';" ^
  "$s.Save()"
if errorlevel 1 (
    echo [ERRO] Nao foi possivel criar o atalho.
    pause
    exit /b 1
)
echo.
echo Pronto: atalho "%LNKNAME%" criado na Area de Trabalho.
echo Nao apague nem mova esta pasta: o atalho aponta para ela.
pause
