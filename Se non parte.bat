@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONHOME=
set PYTHONPATH=
set PYTHONSTARTUP=
echo Avvio di Fan Porter in modalita' diagnostica...
echo.
"%~dp0python.exe" -E "%~dp0app.py" > "%~dp0avvio-log.txt" 2>&1
type "%~dp0avvio-log.txt"
echo.
echo Se vedi un errore qui sopra, mandalo a chi ti aiuta. Il testo e' anche in avvio-log.txt
pause
