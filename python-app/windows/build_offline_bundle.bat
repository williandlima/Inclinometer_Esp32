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
echo  Isso e so a pasta offline_packages do CD(1) DAD. Antes de gravar
echo  o CD(1), baixar tambem (uma vez, nesta mesma maquina com internet)
echo  e copiar para a raiz do CD(1):
echo    - Instalador do Python 3.10+ (python.org/downloads/windows)
echo    - Instalador do VS Code, "User Installer" x64
echo      (code.visualstudio.com/download) - editor usado no
echo      desenvolvimento do software, alem do proprio Python.
echo.
echo  Depois: copiar a pasta python-app INTEIRA para o CD(2) DSF (sem
echo  a pasta offline_packages, que fica so no CD1). Na maquina de
echo  destino (sem internet), windows\install.bat detecta a pasta
echo  offline_packages copiada do CD(1) e instala a partir dela.
echo ============================================
pause
