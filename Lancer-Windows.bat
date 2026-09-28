@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Menu Caillou - mise a jour des prix
where py >nul 2>nul
if %errorlevel%==0 (
  py maj_prix.py
  goto fin
)
where python >nul 2>nul
if %errorlevel%==0 (
  python maj_prix.py
  goto fin
)
echo.
echo Python n'est pas installe sur cet ordinateur.
echo Une page va s'ouvrir : telecharge et installe Python (coche Add python.exe to PATH),
echo puis double-clique de nouveau sur ce fichier.
start https://www.python.org/downloads/
:fin
echo.
pause
