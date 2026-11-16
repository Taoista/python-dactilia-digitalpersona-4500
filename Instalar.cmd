@echo off
setlocal
cd /d "%~dp0"
py -3.14 instalar.py
if errorlevel 1 (
 echo Instalacion incompleta. Consulta README.md.
 pause
 exit /b 1
)
echo Instalacion verificada. Ejecuta "Abrir estacion.cmd".
