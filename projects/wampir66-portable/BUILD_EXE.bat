@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-windows.ps1"
if errorlevel 1 (
 echo Budowanie nie powiodlo sie. Sprawdz komunikaty powyzej.
 pause
 exit /b 1
)
pause
