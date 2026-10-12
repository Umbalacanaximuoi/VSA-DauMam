@echo off
chcp 65001 >nul
title KẾT NỐI & ĐẨY LÊN GITHUB TỰ ĐỘNG — VSA ĐẬU MẦM PRO
cd /d "%~dp0"

echo =========================================================================
echo       🚀 KẾT NỐI REPOSITORY GITHUB TỰ ĐỘNG CHO VSA MOBILE APP 2.0
echo =========================================================================
echo.
echo Thư mục sạch và Commit đã sẵn sàng 100%%!
echo.
set /p REPO_URL="👉 Vui lòng dán đường dẫn GitHub Repo của bạn (VD: https://github.com/username/vsa-app.git): "

if "%REPO_URL%"=="" (
    echo.
    echo ⚠️ Bạn chưa nhập đường dẫn repo! Vui lòng thử lại.
    pause
    exit /b
)

set "GIT_CMD=C:\Users\AdminVSA\.mingit\cmd\git.exe"
if not exist "%GIT_CMD%" set "GIT_CMD=git"

echo.
echo [1/3] Đang kết nối Remote Origin tới: %REPO_URL% ...
"%GIT_CMD%" remote remove origin 2>nul
"%GIT_CMD%" remote add origin %REPO_URL%

echo [2/3] Kiểm tra nhánh main...
"%GIT_CMD%" branch -M main

echo [3/3] Đang đẩy toàn bộ mã nguồn lên GitHub (git push -u origin main)...
"%GIT_CMD%" push -u origin main

echo.
if %ERRORLEVEL% EQU 0 (
    echo =========================================================================
    echo   🎉 CHÚC MỪNG! ĐÃ ĐẨY LÊN GITHUB THÀNH CÔNG RỰC RỠ!
    echo =========================================================================
    echo Bây giờ bạn có thể vào https://render.com kết nối repo này để dùng trên điện thoại 24/7!
) else (
    echo.
    echo ⚠️ Nếu gặp lỗi quyền truy cập, vui lòng đảm bảo bạn đã đăng nhập GitHub hoặc dùng Personal Access Token.
)
echo =========================================================================
pause
