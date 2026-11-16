@echo off
cd /d "%~dp0"
title Cap Nhat QC AI - CPC1HN
color 0a

echo =======================================================
echo     CAP NHAT PHIEN BAN MOI TU GITHUB (QC AI CPC1HN)
echo =======================================================
echo.
python --version
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python! Vui long kiem tra lai cai dat Python.
    pause
    exit /b 1
)

python -m core.updater
echo.
pause
