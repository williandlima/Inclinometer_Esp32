@echo off
REM ======================================================================
REM  Instala a versao PORTATIL do Inclinometro 2 Eixos (Avibras Aeroco)
REM  e cria o icone na Area de Trabalho e no Menu Iniciar.
REM  Nao precisa de administrador nem de Python.
REM
REM  O que ele faz:
REM   1) acha o programa: nesta pasta, numa subpasta Inclinometro2Eixos,
REM      ou o .zip "Inclinometro-2Eixos-Portatil" baixado em Downloads
REM      (e extrai sozinho);
REM   2) copia a pasta inteira para %LOCALAPPDATA%\Programs\Inclinometro2Eixos;
REM   3) tira o bloqueio "baixado da internet" de todos os arquivos
REM      (e isso que faz o Windows tratar o .exe como perigoso);
REM   4) cria os atalhos com a logo e abre o programa.
REM  Opcional: adiciona uma excecao no Windows Defender (pede administrador).
REM ======================================================================

setlocal EnableExtensions
title Instalador - Inclinometro 2 Eixos
set "EXE=Inclinometro2Eixos.exe"
set "DEST=%LOCALAPPDATA%\Programs\Inclinometro2Eixos"
set "LNKNAME=Inclinometro 2 Eixos (Avibras Aeroco)"
set "SRC="
set "TMPX="

echo.
echo === Inclinometro 2 Eixos - instalacao portatil ===
echo.

REM ---- 1) Localiza o programa -----------------------------------------
if exist "%~dp0%EXE%" set "SRC=%~dp0"
if not defined SRC if exist "%~dp0Inclinometro2Eixos\%EXE%" set "SRC=%~dp0Inclinometro2Eixos\"
if not defined SRC (
    for /f "delims=" %%Z in ('powershell -NoProfile -Command "Get-ChildItem -Path ($env:USERPROFILE+'\Downloads'),'%~dp0' -Filter 'Inclinometro-2Eixos-Portatil*.zip' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"') do set "ZIP=%%Z"
)
if not defined SRC if defined ZIP (
    echo Extraindo "%ZIP%" ...
    set "TMPX=%TEMP%\Inclinometro2Eixos_extract"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Unblock-File -LiteralPath $env:ZIP; if (Test-Path $env:TMPX) { Remove-Item $env:TMPX -Recurse -Force }; Expand-Archive -LiteralPath $env:ZIP -DestinationPath $env:TMPX -Force"
)
if not defined SRC if defined TMPX (
    for /f "delims=" %%E in ('powershell -NoProfile -Command "Get-ChildItem -LiteralPath $env:TMPX -Recurse -Filter $env:EXE | Select-Object -First 1 -ExpandProperty DirectoryName"') do set "SRC=%%E\"
)
if not defined SRC (
    echo [ERRO] Nao encontrei o %EXE%.
    echo Coloque este .bat dentro da pasta Inclinometro2Eixos ^(ao lado do .exe^),
    echo ou deixe o "Inclinometro-2Eixos-Portatil.zip" na pasta Downloads.
    goto :fim_erro
)
if not exist "%SRC%_internal" (
    echo [ERRO] A pasta _internal nao esta ao lado do %EXE% em:
    echo   %SRC%
    echo Extraia o .zip inteiro de novo ^(nao copie so o .exe^).
    goto :fim_erro
)
echo Programa encontrado em: %SRC%

REM ---- 2) Fecha o programa se estiver aberto e copia ------------------
taskkill /im "%EXE%" /f >nul 2>nul
echo Copiando para: %DEST%
robocopy "%SRC%." "%DEST%" /MIR /NFL /NDL /NJH /NJS /NP /R:2 /W:1 >nul
if errorlevel 8 (
    echo [ERRO] Falha ao copiar os arquivos.
    goto :fim_erro
)

REM ---- 3) Desbloqueia e 4) cria os atalhos ----------------------------
echo Desbloqueando os arquivos e criando os atalhos...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-ChildItem -LiteralPath $env:DEST -Recurse -File | Unblock-File;" ^
  "$w=New-Object -ComObject WScript.Shell;" ^
  "$exe=Join-Path $env:DEST $env:EXE;" ^
  "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {" ^
  "  $s=$w.CreateShortcut((Join-Path $d ($env:LNKNAME + '.lnk')));" ^
  "  $s.TargetPath=$exe; $s.WorkingDirectory=$env:DEST; $s.IconLocation=$exe + ',0';" ^
  "  $s.Description='Pan-tilt meter - Inclinometro Avibras Aeroco'; $s.Save() }"
if errorlevel 1 (
    echo [ERRO] Nao foi possivel criar os atalhos.
    goto :fim_erro
)
if defined TMPX rd /s /q "%TMPX%" 2>nul

echo.
echo OK: atalho "%LNKNAME%" criado na Area de Trabalho e no Menu Iniciar.
echo.

REM ---- Opcional: excecao no Windows Defender --------------------------
choice /c SN /n /m "O antivirus (Windows Defender) apaga ou bloqueia o programa? Adicionar excecao para a pasta [S/N]? "
if errorlevel 2 goto :abrir
echo Vai abrir a confirmacao de administrador do Windows...
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-Command','Add-MpPreference -ExclusionPath ''%DEST%''; Write-Host Excecao adicionada.; Start-Sleep 3'"
if errorlevel 1 echo [AVISO] Excecao nao adicionada ^(sem permissao de administrador ou antivirus gerenciado pela TI^).

:abrir
echo Abrindo o programa...
start "" "%DEST%\%EXE%"
echo.
echo Pronto. Nas proximas vezes, use o icone da Area de Trabalho.
pause
exit /b 0

:fim_erro
echo.
pause
exit /b 1
