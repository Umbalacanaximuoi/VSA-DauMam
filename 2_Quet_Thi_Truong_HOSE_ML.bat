@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title VSA Đậu Mầm Pro - Quét Lọc Sàn HOSE Bằng Machine Learning

set "PY_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%USERPROFILE%\.venv\Scripts\python.exe" (
    set "PY_EXE=%USERPROFILE%\.venv\Scripts\python.exe"
)

:MENU
cls
echo =======================================================================
echo        🚀 VSA ĐẬU MẦM PRO - BỘ LỌC MACHINE LEARNING TOÀN SÀN HOSE
echo =======================================================================
echo.
echo Lựa chọn:
echo   [1] Quét phiên giao dịch mới nhất (Mặc định)
echo   [2] Quét một ngày cụ thể trong lịch sử (VD: 2021-08-11, 2024-03-08...)
echo   [3] Thoát
echo.
set "CHOICE="
set /p CHOICE="👉 Lựa chọn của bạn (1/2/3, bấm Enter để chọn 1): "

if "%CHOICE%"=="" set "CHOICE=1"
if "%CHOICE%"=="1" (
    echo.
    echo Đang quét toàn bộ các mã trên sàn HOSE bằng Machine Learning...
    echo -----------------------------------------------------------------------
    "!PY_EXE!" "%~dp0run_scan_ml.py"
    echo.
    pause
    goto MENU
)
if "%CHOICE%"=="2" (
    echo.
    set "SCAN_DATE="
    set /p SCAN_DATE="👉 Nhập ngày cần quét (định dạng YYYY-MM-DD): "
    if not "!SCAN_DATE!"=="" (
        echo.
        echo Đang quét dữ liệu sàn HOSE ngày !SCAN_DATE!...
        echo -----------------------------------------------------------------------
        "!PY_EXE!" "%~dp0run_scan_ml.py" !SCAN_DATE!
    )
    echo.
    pause
    goto MENU
)
if "%CHOICE%"=="3" exit /b
goto MENU
