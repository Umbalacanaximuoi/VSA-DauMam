# HƯỚNG DẪN HOÀN THIỆN PHIÊN BẢN DI ĐỘNG (MOBILE WEB APP 2.0) & GITHUB
**Hệ Thống Phân Tích Cung Cầu & Săn Siêu Cổ Phiếu Nền Số 2 — VSA Đậu Mầm Pro**

---

## 📱 1. CÁC TÍNH NĂNG MỚI TRÊN PHIÊN BẢN MOBILE 2.0

Phiên bản di động được thiết kế chuyên biệt theo chuẩn **Mobile-First (giao diện dọc)**, tối ưu cho màn hình cảm ứng điện thoại (iPhone, Samsung, Xiaomi...) với Dark Mode cao cấp và tốc độ tải tức thì:

### 🌟 4 Thang Điểm Cốt Lõi (Thang 0 – 100đ):
1. 🧭 **ĐIỂM VSA (VSA Score):** Đo lường mức độ kiểm soát của dòng tiền lớn và chênh lệch Cung - Cầu.
2. 🎯 **ĐIỂM BDI (VSA Design Index):** Đánh giá độ hoàn thiện cấu trúc nền giá theo 8 tiêu chí VSA chuẩn mực.
3. 🔥 **ĐIỂM BMS (Xung Lực BDI Momentum):** Đo lường động lượng nén lò xo và phân hạng xung lực (Hạng S, A, B, C).
4. 🏆 **ĐIỂM No2 (Chiến Lược Nền 2):** Đo lường độ chuẩn của cấu trúc Nền Giá Số 2 Trên Cao (Stage 1 Markup, Nén VCP, Kiệt Cung C1, Pocket Pivot P1).

### 🏆 Tab Radar Nền 2 (No2) Ngay Trên Điện Thoại:
- Bấm chuyển tab **"🏆 Radar Nền 2 (No2)"** để xem danh sách các mã đang nén chặt nền 2 trên toàn thị trường (như SBG, VOS, TCB,...).
- Hiển thị đầy đủ: Điểm No2, Điểm BMS, Badge hành động (C1 Kiệt Cung / P1 Pocket / B1 Bứt Nền), % Nhịp tăng 1, Số phiên nền, Độ sâu điều chỉnh.
- Chạm vào bất kỳ cổ phiếu nào trên radar $\rightarrow$ Ứng dụng tự động chuyển sang trang bóc tách chi tiết!

### 📐 Bóc Tách 6 Tầng Định Lượng No2 & Kế Hoạch Đi Vốn:
- Nút bấm xem chi tiết 6 tầng: Nhịp 1, Xu hướng MA50/100, Nén VCP Nền 2, Kiệt Cung VDU, Tiền ngầm SMD, Kích hoạt BMS.
- Kế hoạch giải ngân chuẩn xác: Điểm cược C1 (1/8 NAV), Điểm kích hoạt P1 (1/4 NAV), Điểm bứt nền B1, Mức cắt lỗ kỷ luật và Vùng mục tiêu lợi nhuận (+35% đến +60%).

---

## 🚀 2. CÁCH 1: DÙNG TRÊN ĐIỆN THOẠI NGAY LẬP TỨC (QUA WI-FI NỘI BỘ)

Bạn có thể mở ứng dụng trên điện thoại ngay bây giờ mà không cần kết nối GitHub:

1. **Bước 1:** Nhấp đúp chuột vào file:
   ```
   Chay_App_Mobile.bat
   ```
2. **Bước 2:** Cửa sổ màn hình sẽ tự động nhận diện IP máy tính và thông báo:
   ```
   👉 Trên Máy tính:   http://localhost:8000/mobile
   👉 Trên Điện thoại:  http://192.168.1.xxx:8000/mobile
   ```
3. **Bước 3:** Trên điện thoại, mở trình duyệt **Safari (iPhone)** hoặc **Chrome (Android)** và truy cập địa chỉ IP hiển thị ở Bước 2.
4. **Bước 4 (Cài thành App trên màn hình chính):**
   - **Trên iPhone (Safari):** Bấm nút Chia sẻ (biểu tượng hình vuông có mũi tên lên) $\rightarrow$ Chọn **"Thêm vào MH chính" (Add to Home Screen)**.
   - **Trên Android (Chrome):** Bấm dấu 3 chấm góc trên bên phải $\rightarrow$ Chọn **"Thêm vào màn hình chính"**.
   - Biểu tượng ứng dụng VSA Đậu Mầm sẽ xuất hiện ngoài màn hình điện thoại, mở lên toàn màn hình như ứng dụng tải từ App Store!

---

## 🌐 3. CÁCH 2: ĐẨY LÊN GITHUB ĐỂ SỬ DỤNG 4G/5G NGOÀI ĐƯỜNG 24/7

Toàn bộ mã nguồn sạch, đã lọc bỏ các file nặng quá 100MB và bảo vệ dữ liệu nhạy cảm, đã được chuẩn bị sẵn sàng tại thư mục:
```
C:\Users\AdminVSA\.gemini\antigravity\scratch\vsa_github_ready
```

### Các bước đẩy lên GitHub:
1. Mở Terminal / PowerShell tại thư mục `vsa_github_ready`:
   ```bash
   cd C:\Users\AdminVSA\.gemini\antigravity\scratch\vsa_github_ready
   git init
   git add .
   git commit -m "feat: Ban Mobile Web App 2.0 voi Chien Luoc No2 & Radar"
   git branch -M main
   git remote add origin https://github.com/<tai-khoan-cua-ban>/vsa-mobile-app.git
   git push -u origin main
   ```

2. **Triển khai miễn phí lên Render.com (hoặc Hugging Face):**
   - Đăng nhập [render.com](https://render.com) $\rightarrow$ New **Web Service** $\rightarrow$ Chọn Repository vừa tạo.
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - Render sẽ cấp một đường link trực tuyến 24/7 dạng:
     ```
     https://vsa-mobile-app.onrender.com/mobile
     ```
   - Bạn có thể lưu link này trên điện thoại để tra cứu cổ phiếu và săn siêu cổ Nền 2 mọi lúc, mọi nơi bằng 4G/5G!

================================================================================
