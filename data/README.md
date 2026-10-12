# Thư mục dữ liệu cục bộ (Local Data Folder)

Đặt các file dữ liệu xuất từ Amibroker hoặc Fireant MetaKit vào thư mục này để hệ thống ưu tiên đọc dữ liệu cục bộ trước khi tải từ API vnstock.

## Định dạng File
Tên file phải khớp với mã cổ phiếu viết hoa (Ví dụ: `FPT.csv`, `HPG.csv`).

Định dạng file CSV cần chứa các cột cơ bản sau:
- `Ticker` (hoặc `Symbol`) - Mã cổ phiếu.
- `Date/Time` (hoặc `Date`, `DateTime`, `Time`) - Thời gian giao dịch.
- `Open` - Giá mở cửa.
- `High` - Giá cao nhất.
- `Low` - Giá thấp nhất.
- `Close` - Giá đóng cửa.
- `Volume` - Khối lượng giao dịch.

*Lưu ý: Hệ thống tự động chuẩn hóa chữ hoa/thường và khoảng trắng của tên cột khi tải.*
