@echo off

:: ============================================================
:: VALIDAÇÃO DE PROBABILIDADES - V2.0
:: ============================================================

title RefStats - Validação V2.0

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║     VALIDAÇÃO DE PROBABILIDADES - V2.0                       ║
echo ║    Brier Score • Log Loss • Curva de Confiabilidade          ║
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

python -c "import bs4; import requests" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Instalando dependências...
    pip install --upgrade pip >nul 2>&1
    pip install beautifulsoup4 requests
    echo [OK] Instalado.
) else (
    echo [OK] Dependências OK.
)
echo.

:: Cria pastas
if not exist "Probabilidade" mkdir Probabilidade
if not exist "Probabilidade\Relatorio" mkdir "Probabilidade\Relatorio"

:: Executa
echo [4/4] Executando validação...
echo.
echo ────────────────────────────────────────────────────────────────
echo.

python validar_probabilidades_v2.py

echo.
echo ────────────────────────────────────────────────────────────────
echo.
echo [OK] Processamento concluído!
echo     Relatórios em: %cd%\Probabilidade\Relatorio\
echo.

deactivate
pause
