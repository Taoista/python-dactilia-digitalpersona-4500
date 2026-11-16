@echo off
setlocal
set "DACTILIA_SCRIPT=%~dp0estacion.py"
if not exist "%~dp0.venv\Scripts\python.exe" (
 echo Ejecuta Instalar.cmd primero.
 pause
 exit /b 1
)
for /f "delims=" %%P in ('py -3.14 -c "import sys; print(sys.executable)"') do set "DACTILIA_PY=%%P"
powershell -NoProfile -Command "$q=[char]34; $arg=$q+$env:DACTILIA_PY+$q+' -B '+$q+$env:DACTILIA_SCRIPT+$q; Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\conhost.exe') -ArgumentList $arg -Verb RunAs"
