@echo off
REM Gera o instalador Windows (Setup.exe) do Inclinometro Avibras Aeroco:
REM 1) empacota o app com PyInstaller (windows\build_exe.bat)
REM 2) compila o instalador com o Inno Setup (windows\Inclinometro.iss)
REM
REM Requer o Inno Setup instalado: https://jrsoftware.org/isinfo.php
REM (instala o compilador de linha de comando ISCC.exe usado abaixo).
REM Precisa ser executado em uma maquina Windows.

cd /d "%~dp0"

call build_exe.bat
if not exist "..\dist\Inclinometro2Eixos\Inclinometro2Eixos.exe" (
    echo [ERRO] Executavel nao foi gerado. Veja os erros acima.
    exit /b 1
)

echo.
echo Procurando o compilador do Inno Setup (ISCC.exe)...

set ISCC=""
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
where ISCC.exe >nul 2>nul && set ISCC=ISCC.exe

if %ISCC%=="" (
    echo [ERRO] Inno Setup nao encontrado.
    echo Baixe e instale em: https://jrsoftware.org/isdl.php
    echo ^(basta o instalador padrao, nao precisa de opcoes extras^)
    pause
    exit /b 1
)

echo Compilando o instalador...
%ISCC% Inclinometro.iss
if errorlevel 1 (
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Instalador gerado em:
echo  windows\installer_output\Inclinometro-2Eixos-Setup-2.0.0.exe
echo.
echo  Esse arquivo unico pode ser copiado para qualquer
echo  computador Windows (10/11, 64 bits) e instala o
echo  programa com atalhos e desinstalador, sem precisar
echo  de Python instalado.
echo ============================================
pause
