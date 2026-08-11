@echo off
REM Instalador de dependencias do Inclinometro Avibras Aeroco (Windows).
REM Cria um ambiente virtual isolado em python-app\.venv e instala tudo
REM que esta em requirements.txt, sem alterar o Python global do sistema.

setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo ============================================
echo  Inclinometro Avibras Aeroco - Instalador
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao foi encontrado no PATH.
    echo.
    echo Instale o Python 3.10 ou superior em:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANTE: na tela de instalacao do Python, marque a opcao
    echo "Add python.exe to PATH" antes de clicar em Install.
    echo.
    pause
    exit /b 1
)

echo Verificando versao do Python...
python --version

echo.
echo Criando ambiente virtual em ".venv"...
python -m venv .venv
if errorlevel 1 (
    echo [ERRO] Falha ao criar o ambiente virtual.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo.
echo Atualizando pip...
python -m pip install --upgrade pip

echo.
echo Instalando dependencias do software (isso pode levar alguns minutos)...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao instalar as dependencias. Verifique sua conexao
    echo com a internet ^(ou configuracoes de proxy^) e tente novamente.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Instalacao concluida com sucesso!
echo.
echo  Para abrir o software, use: windows\run.bat
echo ============================================
pause
