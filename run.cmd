@echo off
setlocal
cd /d "%~dp0"

curl.exe --silent --fail http://127.0.0.1:5000/health >nul 2>&1
if not errorlevel 1 (
    echo O site ja esta rodando em http://127.0.0.1:5000
    exit /b 0
)

if exist ".venv\Scripts\python.exe" goto use_venv
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" goto use_installed_python

echo Python nao encontrado. Instale o Python ou crie o ambiente .venv do projeto.
exit /b 1

:use_venv
set "site_python=%~dp0.venv\Scripts\python.exe"
goto start_site

:use_installed_python
set "site_python=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"

:start_site
"%site_python%" -m flask --app run.py preparar-banco
if errorlevel 1 (
    echo Nao foi possivel atualizar o banco. O servidor nao foi iniciado.
    exit /b 1
)
echo Iniciando o site em http://127.0.0.1:5000
"%site_python%" -m flask --app run.py run --debug
exit /b %errorlevel%
