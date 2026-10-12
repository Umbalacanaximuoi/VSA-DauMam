@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title VSA Đậu Mầm Pro - Zero Loss Trading

echo ========================================================
echo        🚀 ĐANG KHỞI ĐỘNG VSA ĐẬU MẦM PRO...
echo ========================================================
echo.

set "PY_EXE=python"

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%USERPROFILE%\.venv\Scripts\python.exe" (
    set "PY_EXE=%USERPROFILE%\.venv\Scripts\python.exe"
)

echo Đang chạy bằng Python: !PY_EXE!
echo Máy chủ đang mở tại: http://127.0.0.1:8000
echo Trang Quản Trị Admin: http://127.0.0.1:8000/admin
echo.

"!PY_EXE!" desktop_app.py

pause
