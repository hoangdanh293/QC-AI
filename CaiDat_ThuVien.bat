@echo off
title Cai Dat Thu Vien QC AI - CPC1HN
color 0b

echo =======================================================
echo     CHUONG TRINH CAI DAT THU VIEN TU DONG (QC AI)
echo =======================================================
echo.
echo Dang kiem tra phien ban Python...
python --version
if %errorlevel% neq 0 (
    echo.
    echo [LOI] May tinh nay chua cai dat Python! Vui long cai Python truoc.
    echo.
    pause
    exit
)

echo.
echo Dang tien hanh tai va cai dat cac thu vien can thiet...
echo Qua trinh nay co the mat 1-2 phut can co ket noi mang.
echo.

python -m pip install --upgrade pip
if exist "%~dp0requirements.txt" (
    python -m pip install -r "%~dp0requirements.txt"
) else (
    python -m pip install streamlit requests pymupdf docxtpl python-docx google-genai langchain-text-splitters openai easyocr pypdf pdfplumber bcrypt cryptography Pillow google-api-python-client google-auth-httplib2 google-auth-oauthlib
)

echo.
echo =======================================================
echo   CAI DAT HOAN TAT!
echo   HE THONG DA SAN SANG DE CHAY.
echo   Ban co the dong cua so nay va mo file Khoi Dong.
echo =======================================================
pause
