@echo off

:: ============================================================
:: ANÁLISE PROBABILÍSTICA DE CARTÕES - V2.0
:: ============================================================

title RefStats - Análise Probabilística V2.0

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║     REFSTATS - ANÁLISE PROBABILÍSTICA V2.0                   ║
echo ║  Neg. Binomial + Shrinkage + Calibração + Intervalos         ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"
echo [INFO] Diretório: %cd%
echo.

:: Verifica Python
echo [1/4] Verificando Python...
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python não encontrado!
    pause
    exit /b 1
)
echo [OK] Python encontrado.
echo.

:: Verifica/cria venv
echo [2/4] Verificando ambiente virtual...
if exist "venv\Scripts\activate.bat" (
    echo [OK] Ambiente virtual encontrado.
) else (
    echo [INFO] Criando ambiente virtual...
    python -m venv venv
    echo [OK] Ambiente criado.
)
echo.

:: Ativa venv e instala dependências
echo [3/4] Ativando ambiente e verificando dependências...
call venv\Scripts\activate.bat

python -c "import bs4" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Instalando beautifulsoup4...
    pip install --upgrade pip >nul 2>&1
    pip install beautifulsoup4
    echo [OK] Instalado.
) else (
    echo [OK] Dependências OK.
)
echo.

:: Cria pastas
if not exist "Historico" mkdir Historico
if not exist "Probabilidade" mkdir Probabilidade
if not exist "Calibracao" mkdir Calibracao

:: Executa
echo [4/4] Executando análise...
echo.
echo ────────────────────────────────────────────────────────────────
echo.

python probabilidade_cartoes_v2.py

echo.
echo ────────────────────────────────────────────────────────────────
echo.
echo [OK] Processamento concluído!
echo     Arquivos salvos em: %cd%\Probabilidade\
echo.

deactivate
pause
