@echo off
cd /d "%~dp0"
if not exist "Wampir66_Monitor_Portable.exe" (
 echo Brak EXE. Uruchom ten plik z folderu rozpakowanej wersji portable.
 pause
 exit /b 1
)
start "" "%~dp0Wampir66_Monitor_Portable.exe"
