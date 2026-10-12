@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title VSA Đậu Mầm Pro — Máy Chủ Mobile & GitHub

echo ========================================================
echo   📱 ĐANG KHỞI ĐỘNG VSA ĐẬU MẦM PRO — PHIÊN BẢN DI ĐỘNG
echo ========================================================
echo.

set "PY_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%USERPROFILE%\.venv\Scripts\python.exe" (
    set "PY_EXE=%USERPROFILE%\.venv\Scripts\python.exe"
)

:: Tìm địa chỉ IP nội bộ của máy tính
set "LOCAL_IP=127.0.0.1"
for /f "tokens=4" %%a in ('route print 0.0.0.0 ^| findstr "0.0.0.0" 2^>nul') do (
    if not "%%a"=="" set "LOCAL_IP=%%a"
)

echo [✓] Đang chạy với Python: !PY_EXE!
echo.
echo ========================================================
echo   🌐 ĐƯỜNG DẪN TRUY CẬP TRÊN THIẾT BỊ:
echo ========================================================
echo  👉 Trên Máy tính:   http://localhost:8000/mobile
echo  👉 Trên Điện thoại:  http://!LOCAL_IP!:8000/mobile
echo     (Chỉ cần điện thoại kết nối chung mạng Wi-Fi)
echo ========================================================
echo.
echo Đang mở trình duyệt thử nghiệm...
start http://localhost:8000/mobile

echo.
echo Máy chủ đang lắng nghe tại 0.0.0.0:8000 (Nhấn Ctrl+C để dừng)...
echo.
"!PY_EXE!" -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

pause
