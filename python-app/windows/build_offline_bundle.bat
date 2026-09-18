@echo off
REM Prepara o pacote de instalacao OFFLINE do software desktop.
REM
REM Rodar esta etapa numa maquina COM internet (ex.: no ambiente de
REM desenvolvimento). Ela baixa todos os pacotes .whl exigidos por
REM requirements.txt para a pasta windows\offline_packages, ao lado
REM deste script.
REM
REM Depois de gerado, copiar a pasta python-app inteira (incluindo
REM windows\offline_packages) para o DVD/CD do repositorio fisico da
REM fabrica. install.bat detecta essa pasta automaticamente e instala
REM sem precisar de conexao a internet na maquina de destino.

setlocal
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao foi encontrado no PATH.
    echo Esta etapa precisa ser executada numa maquina com Python e
    echo conexao a internet, antes de gravar a midia de instalacao.
    pause
    exit /b 1
)

echo ============================================
echo  Preparando pacote de instalacao OFFLINE
echo ============================================
echo.
echo Baixando pacotes de requirements.txt para windows\offline_packages...
echo (isso precisa de conexao a internet - normal so nesta etapa)
echo.

python -m pip download -r requirements.txt -d windows\offline_packages
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao baixar os pacotes. Verifique a conexao com a internet.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Pacote offline gerado com sucesso em:
echo    windows\offline_packages
echo.
echo  Proximo passo: copiar a pasta python-app INTEIRA (incluindo essa
echo  pasta offline_packages) para o DVD/CD do repositorio fisico da
echo  fabrica. Na maquina de destino (sem internet), windows\install.bat
echo  detecta a pasta automaticamente e instala a partir dela.
echo ============================================
pause
