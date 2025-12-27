@echo off
title Sistema Unificado de Análise v1.0

echo.
echo ══════════════════════════════════════════════════════════════════════
echo   🎯 SISTEMA UNIFICADO DE ANÁLISE DE JOGOS v1.0
echo   Configuração Automática
echo ══════════════════════════════════════════════════════════════════════
echo.

:: Verifica se Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ ERRO: Python não encontrado!
    echo    Por favor, instale o Python 3.8+ e adicione ao PATH.
    echo    Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo ✅ Python encontrado!
python --version
echo.

:: Define o diretório do script
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Nome do ambiente virtual
set "VENV_NAME=venv_unificado"

:: Verifica se o venv já existe
if exist "%VENV_NAME%\Scripts\activate.bat" (
    echo ✅ Ambiente virtual já existe.
    echo.
    goto :activate_venv
)

:: Cria o ambiente virtual
echo 📦 Criando ambiente virtual...
echo    Isso pode demorar alguns segundos...
echo.
python -m venv %VENV_NAME%

if errorlevel 1 (
    echo ❌ ERRO ao criar ambiente virtual!
    echo    Tente executar: python -m pip install --upgrade pip
    echo.
    pause
    exit /b 1
)

echo ✅ Ambiente virtual criado com sucesso!
echo.

:activate_venv
:: Ativa o ambiente virtual
echo 🔄 Ativando ambiente virtual...
call "%VENV_NAME%\Scripts\activate.bat"

if errorlevel 1 (
    echo ❌ ERRO ao ativar ambiente virtual!
    pause
    exit /b 1
)

echo ✅ Ambiente virtual ativado!
echo.

:: Atualiza pip
echo 📦 Atualizando pip...
python -m pip install --upgrade pip --quiet
echo.

:: Verifica se as dependências já estão instaladas
python -c "import requests, feedparser" >nul 2>&1
if errorlevel 1 (
    goto :install_deps
) else (
    echo ✅ Dependências já instaladas.
    echo.
    goto :run_program
)

:install_deps
echo ══════════════════════════════════════════════════════════════════════
echo   📦 INSTALANDO DEPENDÊNCIAS
echo ══════════════════════════════════════════════════════════════════════
echo.

:: Cria arquivo requirements.txt temporário
echo requests>=2.28.0> requirements_temp.txt
echo feedparser>=6.0.0>> requirements_temp.txt
echo beautifulsoup4>=4.11.0>> requirements_temp.txt
echo lxml>=4.9.0>> requirements_temp.txt

echo 📥 Instalando pacotes...
echo.
pip install -r requirements_temp.txt

if errorlevel 1 (
    echo.
    echo ❌ ERRO ao instalar dependências!
    echo    Verifique sua conexão com a internet.
    echo.
    del requirements_temp.txt >nul 2>&1
    pause
    exit /b 1
)

:: Remove arquivo temporário
del requirements_temp.txt >nul 2>&1

echo.
echo ✅ Todas as dependências instaladas com sucesso!
echo.

:run_program
echo ══════════════════════════════════════════════════════════════════════
echo   🚀 EXECUTANDO SISTEMA UNIFICADO
echo ══════════════════════════════════════════════════════════════════════
echo.


:: Executa o programa
python gerar_datas_historico.py

echo.
echo ══════════════════════════════════════════════════════════════════════
echo   ✅ EXECUÇÃO FINALIZADA
echo ══════════════════════════════════════════════════════════════════════
echo.

:: Desativa o ambiente virtual
deactivate >nul 2>&1

pause
