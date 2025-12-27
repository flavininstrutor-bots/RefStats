@echo off
echo ============================================================
echo    RefStats - Tradutor de Jogos para Inglês
echo ============================================================
echo.

REM Verifica se Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python não encontrado!
    echo Por favor, instale o Python em: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Executa o script
python traduzir_jogos.py

echo.
echo Pressione qualquer tecla para fechar...
pause >nul
