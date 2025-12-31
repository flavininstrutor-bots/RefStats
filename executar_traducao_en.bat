@echo off
chcp 65001 >nul
cls

echo ╔═══════════════════════════════════════════════════════════════╗
echo ║           TRADUTOR HTML - PORTUGUÊS → INGLÊS                  ║
echo ║                      RefStats V2.0                            ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

REM Ativa ambiente virtual se existir
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Executa o script Python
python traduzir_html_en.py

echo.
echo Pressione qualquer tecla para fechar...
pause >nul
