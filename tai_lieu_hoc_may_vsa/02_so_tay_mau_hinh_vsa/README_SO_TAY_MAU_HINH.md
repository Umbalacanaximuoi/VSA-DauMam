# SỔ TAY CÁC MẪU HÌNH VSA THỰC CHIẾN CHUẨN HÓA

Thư mục này chứa tập dữ liệu mẫu hình chuẩn mà hệ thống **VSAPatternMatcher** sử dụng để tính toán độ tương đồng (Similarity Score) qua thuật toán **Cosine Similarity** và **Dynamic Time Warping (DTW)**.

---

## 1. Danh Mục Các Mẫu Hình Huấn Luyện

| STT | Mã Tham Chiếu | Tên Mẫu Hình Chuẩn | Giai Đoạn Lịch Sử | Sóng Ngành | Kết Quả Thực Chiến | Đặc Điểm Nhận Diện Cốt Lõi |
| :---: | :---: | :--- | :---: | :---: | :---: | :--- |
| **1** | **DGC** | **VCP Thu Hẹp Biến Độ (3 lần co thắt)** | 01/06/2021 $\rightarrow$ 11/08/2021 | Hóa chất | **Thành công (+120%)** | Nền siết chặt 3 nhịp biên độ nhỏ dần, kiệt quệ khối lượng trước phiên nổ, có sóng ngành bảo trợ. |
| **2** | **FRT** | **Gãy Nền Rũ Bỏ (Spring / LPS kiệt cung)** | 15/09/2023 $\rightarrow$ 04/10/2023 | Bán lẻ | **Thành công (+75%)** | Rũ gãy hỗ trợ ngắn hạn để ép nhỏ lẻ cắt lỗ, sau đó hồi phục test cung vol siêu cạn rồi bứt phá. |
| **3** | **SSI** | **Vượt Cản Chéo Kênh Xu Hướng Dốc Xuống** | 10/11/2020 $\rightarrow$ 01/12/2020 | Chứng khoán | **Thành công (+150%)** | Thoát khỏi kênh chéo tích lũy lớn nhiều tháng, toàn bộ dòng chứng khoán đồng loạt vào sóng lớn. |
| **4** | **NVL** | **Breakout Thất Bại (Zero Đỉnh / Bulltrap)** | 10/08/2022 $\rightarrow$ 25/08/2022 | Bất động sản | **Thất bại (-25%)** | Nổ Breakout vol lớn nhưng T+2 gãy quá 50% thân nến nổ, thị trường chung downtrend phân phối. |

---

## 2. Quy Cách Cung Cấp Mẫu Hình Mới

Khi bạn có các case study mới (mẫu hình thành công hoặc thất bại), bạn có thể bổ sung trực tiếp vào:
* File Excel: [**`so_tay_mau_hinh_vsa.xlsx`**](file:///C:/Users/AdminVSA/.gemini/antigravity/scratch/vsa_daumam_pro/tai_lieu_hoc_may_vsa/02_so_tay_mau_hinh_vsa/so_tay_mau_hinh_vsa.xlsx)
* Hoặc file CSV: [**`so_tay_mau_hinh_vsa.csv`**](file:///C:/Users/AdminVSA/.gemini/antigravity/scratch/vsa_daumam_pro/tai_lieu_hoc_may_vsa/02_so_tay_mau_hinh_vsa/so_tay_mau_hinh_vsa.csv)

Hệ thống sẽ tự động vector hóa chuỗi giá và khối lượng của cổ phiếu tham chiếu trong giai đoạn đó để mở rộng thư viện mẫu hình nhận diện của AI!
