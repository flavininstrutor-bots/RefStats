@echo off

:: ============================================================
:: EXECUTAR ANÁLISE PROBABILÍSTICA DE CARTÕES
:: ============================================================
:: Este script:
::   1. Verifica se existe ambiente virtual (venv)
::   2. Cria o venv se não existir
::   3. Atualiza as dependências
::   4. Executa o programa Python
:: ============================================================

title RefStats - Análise Probabilística de Cartões

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║     REFSTATS - ANÁLISE PROBABILÍSTICA DE CARTÕES             ║
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
    echo        Instale o Python em: https://www.python.org/downloads/
    echo        Marque "Add Python to PATH" durante a instalação.
    pause
    exit /b 1
)

:: Mostra versão do Python
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
    echo.
    python -m venv venv
    
    if %ERRORLEVEL% NEQ 0 (
        echo [ERRO] Falha ao criar ambiente virtual!
        pause
        exit /b 1
    )
    
    echo [OK] Ambiente virtual criado com sucesso.
)
echo.

:: ============================================================
:: ATIVAÇÃO DO VENV
:: ============================================================
echo [3/4] Ativando ambiente virtual e verificando dependências...

call venv\Scripts\activate.bat

if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Falha ao ativar ambiente virtual!
    pause
    exit /b 1
)

:: ============================================================
:: INSTALAÇÃO/ATUALIZAÇÃO DE DEPENDÊNCIAS
:: ============================================================

:: Verifica se beautifulsoup4 está instalado
python -c "import bs4" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Instalando dependências...
    pip install --upgrade pip >nul 2>&1
    pip install beautifulsoup4
    echo [OK] Dependências instaladas.
) else (
    echo [OK] Dependências já instaladas.
    
    :: Verifica se há atualizações disponíveis (opcional, silencioso)
    pip install --upgrade beautifulsoup4 >nul 2>&1
)
echo.

:: ============================================================
:: VERIFICAÇÃO DAS PASTAS
:: ============================================================
if not exist "Historico" (
    echo [INFO] Criando pasta Historico...
    mkdir Historico
)

if not exist "Probabilidade" (
    echo [INFO] Criando pasta Probabilidade...
    mkdir Probabilidade
)

:: ============================================================
:: EXECUÇÃO DO PROGRAMA
:: ============================================================
echo [4/4] Executando análise probabilística...
echo.
echo ────────────────────────────────────────────────────────────────
echo.

python probabilidade_cartoes.py

echo.
echo ────────────────────────────────────────────────────────────────

:: ============================================================
:: FINALIZAÇÃO
:: ============================================================
if %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Processamento concluído com sucesso!
    echo.
    echo     Os arquivos foram salvos em: %cd%\Probabilidade\
    echo.
) else (
    echo.
    echo [ERRO] Ocorreu um erro durante o processamento.
    echo.
)

:: Desativa o venv
deactivate

echo Pressione qualquer tecla para fechar...
pause >nul
