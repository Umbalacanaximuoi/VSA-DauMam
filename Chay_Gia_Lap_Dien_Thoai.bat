@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title VSA Đậu Mầm Pro — Giả Lập Điện Thoại Trên Desktop

echo ========================================================
echo   📱 ĐANG KHỞI ĐỘNG GIẢ LẬP ĐIỆN THOẠI TRÊN DESKTOP...
echo ========================================================
echo.

set "PY_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%USERPROFILE%\.venv\Scripts\python.exe" (
    set "PY_EXE=%USERPROFILE%\.venv\Scripts\python.exe"
)

echo [✓] Đang chạy với Python: !PY_EXE!
echo.
echo Cửa sổ ứng dụng sẽ xuất hiện với tỉ lệ chuẩn điện thoại (iPhone 16 Pro Max).
echo Bạn có thể nhập mã, chấm điểm và test trực tiếp các chức năng.
echo.

"!PY_EXE!" "%~dp0run_mobile_simulator.py"

pause
