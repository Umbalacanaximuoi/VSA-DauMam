@echo off
chcp 65001 >nul
title BOT TELEGRAM VSA ĐẬU MẦM - QUÉT LỆNH & GIÁM SÁT REALTIME
cd /d "%~dp0"

echo =========================================================================
echo   VSA ĐẬU MẦM PRO - BOT TELEGRAM TƯƠNG TÁC 2 CHIỀU & QUÉT ĐIỂM MUA
echo =========================================================================
echo.
echo 📱 Bot đang mở luồng lắng nghe mọi lệnh gửi từ điện thoại của bạn:
echo   • 🏆 Săn Siêu Cổ Nền 2 (No2) - Nén chặt chuẩn 6 tầng (Holdings, Watchlist & Thị trường)
echo   • 💎 Radar Siêu Cổ Phiếu AI (Machine Learning 20 năm)
echo   • ⚡ Cổ phiếu giải phóng năng lượng phiên hôm nay (Xung lực BMS Hạng A)
echo   • 🎯 Kiểm tra Xung Lực BDI (BMS 2 danh mục hoặc gõ 'no2 MÃ', 'xung lực MÃ')
echo   • 🌟 Quét Pivot sàn HOSE (Tầng 3)
echo   • 🌱 Quét Đẩy Nền tất cả (Pocket Pivot Tầng 2)
echo   • 🔥 Quét Nổ Vol Surge (≥2.5x TB10)
echo   • 💼 Xem Danh Mục Nắm Giữ & Kỷ luật RRBDI
echo   • 📡 Xem Radar Watchlist
echo.
echo ⏰ Đồng thời giám sát tự động:
echo   • Mỗi 3 phút (13:01 - 14:46): Quét Xung Lực BMS Giải Phóng Năng Lượng
echo   • Mỗi 5 phút (09:15 - 14:30): Quét Breakout 2 danh mục
echo   • 14:05 (Rà soát toàn thị trường phiên chiều)
echo   • 14:30 (Cảnh báo khẩn cấp trước ATC)
echo   • 15:02 (Tổng kết phiên EOD sau chốt nến Metakit)
echo.
echo [LƯU Ý]: Giữ cửa sổ này mở trong giờ giao dịch để Bot luôn phục vụ bạn trên điện thoại!
echo =========================================================================
echo.

if exist "%~dp0VSA_DauMam_Pro.exe" (
    "%~dp0VSA_DauMam_Pro.exe" --bot
) else if exist "%~dp0..\VSA_DauMam_Pro.exe" (
    "%~dp0..\VSA_DauMam_Pro.exe" --bot
) else if exist "%USERPROFILE%\.venv\Scripts\python.exe" (
    "%USERPROFILE%\.venv\Scripts\python.exe" bot_rrbdi_service.py --mode daemon
) else (
    python bot_rrbdi_service.py --mode daemon
)
pause
