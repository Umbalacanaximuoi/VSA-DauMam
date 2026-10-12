# 🚀 VSA ĐẬU MẦM PRO — MOBILE & DESKTOP SYSTEM
**Hệ Thống Phân Tích Cung Cầu, Đọc Dấu Chân Dòng Tiền Lớn & Quản Trị Rủi Ro Kỷ Luật**

---

## 📱 Phiên Bản Di Động (Mobile-First Web App)
Hệ thống được thiết kế tối ưu 100% cho điện thoại thông minh (iPhone, Android) với các tính năng cốt lõi:
- **Ô nhập liệu cổ phiếu:** Tra cứu bất kỳ mã nào trên 3 sàn HOSE, HNX, UPCOM.
- **Bộ 3 Thang Điểm Cốt Lõi (0 – 100đ):**
  - 🧭 **ĐIỂM VSA:** Đánh giá mức độ kiểm soát của Bên Mua/Bên Bán trên thanh nến.
  - 🎯 **ĐIỂM BDI:** Đánh giá cấu trúc tích lũy nền giá theo 8 tiêu chí VSA chuẩn mực.
  - 🔥 **ĐIỂM BMS:** Đo lường xung lực nén lò xo và giải phóng năng lượng.
- **4 Trạng Thái Khuyến Nghị Thực Chiến:**
  - 🎯 **Cược C:** Kiệt cung nền siết — Cân nhắc đưa vào danh mục theo dõi (Tầng 1/4).
  - 🌱 **Pivot P:** Đẩy nền Pocket Pivot — Lò xo bung chốt, bạn nên có mặt (Tầng 2/4).
  - 🚀 **Breakout B:** Xác nhận bứt phá Pha E — Chuyến tàu cuối cùng cho vị thế chuẩn (Tầng 3/4).
  - 👁️ **Quan sát:** Chưa xuất hiện điểm xác nhận — Kiên nhẫn bảo toàn vốn.
- **5 Thước Đo Bóc Tách Cung Cầu:** 100% sử dụng thuật ngữ đọc hành vi (RS, VDU, VCP, SMD, PA), không sử dụng các chỉ báo kỹ thuật cơ học thô.

---

## 💻 Cài Đặt & Khởi Chạy

### 1. Yêu Cầu Hệ Thống
- Python 3.10 trở lên.
- Cài đặt các thư viện phụ thuộc:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Khởi Chạy Trên Máy Tính & Mở Trực Tiếp Trên Điện Thoại
- **Trên Windows:** Nhấp đúp chuột vào file:
  ```cmd
  Chay_App_Mobile.bat
  ```
- **Hoặc chạy bằng dòng lệnh:**
  ```bash
  uvicorn app:app --host 0.0.0.0 --port 8000 --reload
  ```
- **Đường dẫn truy cập:**
  - 📱 Giao diện Di động (Mobile): `http://localhost:8000/mobile`
  - 💻 Giao diện Máy tính (Desktop): `http://localhost:8000/`
  - 📱 Trên Điện thoại cùng mạng Wi-Fi: `http://<IP_MÁY_TÍNH>:8000/mobile`
