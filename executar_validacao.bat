@echo off

:: ============================================================
:: VALIDAÇÃO DE PROBABILIDADES - BACKTESTING
:: ============================================================

title RefStats - Validação de Probabilidades

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║     VALIDAÇÃO DE PROBABILIDADES - BACKTESTING                ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

:: Define o diretório do script como diretório de trabalho
cd /d "%~dp0"
echo [INFO] Diretório de trabalho: %cd%
echo.

:: ============================================================
:: VERIFICAÇÃO DO PYTHON
:: ============================================================
echo [1/4] Verificando instalação do Python...

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python não encontrado no PATH!
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] %PYTHON_VERSION% encontrado.
echo.

:: ============================================================
:: VERIFICAÇÃO/CRIAÇÃO DO VENV
:: ============================================================
echo [2/4] Verificando ambiente virtual (venv)...

if exist "venv\Scripts\activate.bat" (
    echo [OK] Ambiente virtual encontrado.
) else (
    echo [INFO] Ambiente virtual não encontrado. Criando...
    python -m venv venv
    
    if %ERRORLEVEL% NEQ 0 (
        echo [ERRO] Falha ao criar ambiente virtual!
        pause
        exit /b 1
    )
    
    echo [OK] Ambiente virtual criado.
)
echo.

:: ============================================================
:: ATIVAÇÃO DO VENV
:: ============================================================
echo [3/4] Ativando ambiente virtual e verificando dependências...

call venv\Scripts\activate.bat

:: Verifica dependências
python -c "import bs4; import requests" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Instalando dependências...
    pip install --upgrade pip >nul 2>&1
    pip install beautifulsoup4 requests
    echo [OK] Dependências instaladas.
) else (
    echo [OK] Dependências já instaladas.
)
echo.

:: ============================================================
:: VERIFICAÇÃO DAS PASTAS
:: ============================================================
if not exist "Probabilidade" (
    echo [INFO] Criando pasta Probabilidade...
    mkdir Probabilidade
)

if not exist "Probabilidade\Relatorio" (
    echo [INFO] Criando pasta Probabilidade\Relatorio...
    mkdir "Probabilidade\Relatorio"
)

:: ============================================================
:: EXECUÇÃO DO PROGRAMA
:: ============================================================
echo [4/4] Executando validação...
echo.
echo ────────────────────────────────────────────────────────────────
echo.

python validar_probabilidades.py

echo.
echo ────────────────────────────────────────────────────────────────

:: ============================================================
:: FINALIZAÇÃO
:: ============================================================
echo.
echo [OK] Processamento concluído!
echo.
echo     Relatórios salvos em: %cd%\Probabilidade\Relatorio\
echo.

deactivate

echo Pressione qualquer tecla para fechar...
pause >nul
