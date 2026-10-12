@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title VSA Đậu Mầm Pro - Chẩn Đoán Cổ Phiếu Bằng Machine Learning

set "PY_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%USERPROFILE%\.venv\Scripts\python.exe" (
    set "PY_EXE=%USERPROFILE%\.venv\Scripts\python.exe"
)

:INPUT_LOOP
cls
echo =======================================================================
echo        🌱 VSA ĐẬU MẦM PRO - CHẨN ĐOÁN MACHINE LEARNING & MẪU HÌNH
echo =======================================================================
echo.
echo Hướng dẫn:
echo   - Nhập mã cổ phiếu cần chẩn đoán (ví dụ: PVD, SSI, HPG, DGC, FRT...)
echo   - Hoặc nhập kèm ngày lịch sử cần soi (ví dụ: DGC 2021-08-11)
echo   - Gõ 'exit' hoặc đóng cửa sổ để thoát.
echo.
set "USER_INPUT="
set /p USER_INPUT="👉 Nhập mã cổ phiếu: "

if "%USER_INPUT%"=="" goto INPUT_LOOP
if /i "%USER_INPUT%"=="exit" exit /b
if /i "%USER_INPUT%"=="quit" exit /b

echo.
echo Đang tính toán xác suất 3 Tầng và so khớp mẫu hình 20 năm dữ liệu HOSE...
echo -----------------------------------------------------------------------
"!PY_EXE!" "%~dp0run_predict.py" %USER_INPUT%

echo.
echo =======================================================================
echo Bấm phím bất kỳ để tiếp tục chẩn đoán mã khác...
pause > nul
goto INPUT_LOOP
