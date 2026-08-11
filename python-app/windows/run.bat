@echo off
REM Abre o Inclinometro Avibras Aeroco usando o ambiente virtual criado
REM por windows\install.bat. Rode install.bat primeiro, uma unica vez.

cd /d "%~dp0.."

if not exist ".venv\Scripts\activate.bat" (
    echo [ERRO] Ambiente virtual nao encontrado.
    echo Execute primeiro "windows\install.bat".
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python main.py

if errorlevel 1 (
    echo.
    echo O programa foi encerrado com um erro ^(mensagem acima^).
    pause
)
