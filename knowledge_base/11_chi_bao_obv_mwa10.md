# CHỈ BÁO OBV (ON-BALANCE VOLUME) VỚI ĐƯỜNG LÀM MỊN MWA 10 (WEIGHTED MOVING AVERAGE)

Tài liệu chuẩn hóa định nghĩa, công thức toán học, ý nghĩa hành vi dòng tiền Smart Money và quy tắc ứng dụng thực chiến của **Chỉ báo OBV kết hợp đường làm mịn MWA 10** trong hệ thống đầu cơ **VSA Đậu Mầm Pro**.

---

## 1. Bản Chất & Định Nghĩa Cốt Lõi Của OBV (On-Balance Volume)

* **Tên gọi**: On-Balance Volume (Chỉ báo Khối Lượng Cân Bằng) - Được phát triển bởi Joseph Granville (1963).
* **Bản chất VSA**: 
  - OBV là chỉ báo đo lường **dòng tiền tích lũy (Accumulation) và phân phối (Distribution)** của tổ chức (Smart Money) thông qua việc cộng dồn khối lượng giao dịch dựa trên chiều hướng biến động của giá đóng cửa.
  - Khối lượng đi trước giá (*"Volume precedes price"*): Khi dòng tiền lớn bắt đầu gom hàng, OBV sẽ tăng lên trước khi giá bứt phá; ngược lại khi tổ chức âm thầm phân phối, OBV sẽ suy yếu và gãy trước khi giá lao dốc.

---

## 2. Công Thức Toán Học Tính Toán OBV

Khối lượng cân bằng tại phiên thứ $t$ ($\text{OBV}_t$) được tính lũy kế so với phiên trước $t-1$:

$$\text{OBV}_t = \begin{cases} 
\text{OBV}_{t-1} + \text{Volume}_t & \text{nếu } \text{Close}_t > \text{Close}_{t-1} \quad \text{(Phiên tăng giá: Cầu kiểm soát)} \\ 
\text{OBV}_{t-1} - \text{Volume}_t & \text{nếu } \text{Close}_t < \text{Close}_{t-1} \quad \text{(Phiên giảm giá: Cung ép bán)} \\ 
\text{OBV}_{t-1} & \text{nếu } \text{Close}_t = \text{Close}_{t-1} \quad \text{(Tham chiếu: Cân bằng)}
\end{cases}$$

---

## 3. Đường Làm Mịn MWA 10 (Moving Weighted Average 10 Phiên)

### 3.1. Tại sao chọn MWA 10 thay vì SMA 10 hay EMA 10?
* **SMA 10 (Simple Moving Average)**: Gán trọng số cào bằng $10\%$ cho mỗi phiên $\rightarrow$ Quá trễ và phản ứng chậm khi dòng tiền tổ chức đảo chiều đột ngột.
* **EMA 10 (Exponential Moving Average)**: Dùng hàm mũ vô hạn $\rightarrow$ Dễ bị nhiễu bởi các phiên đột biến thanh khoản bất thường.
* **MWA 10 (Moving Weighted Average / WMA 10)**: 
  - Gán **trọng số tuyến tính tăng dần từ 1 đến 10** cho 10 phiên gần nhất. Phiên gần nhất có trọng số lớn gấp 10 lần phiên xa nhất.
  - Tổng trọng số: $\sum_{i=1}^{10} i = 1 + 2 + 3 + \dots + 10 = 55$.
  - **Ưu điểm vượt trội**: Bám sát từng nhịp gom/xả của Smart Money, phản ứng cực nhanh với điểm đổi hướng dòng tiền nhưng vẫn lọc sạch nhiễu giật cục của từng phiên đơn lẻ.

### 3.2. Công thức toán học MWA 10:

$$\text{MWA}_{10}(\text{OBV}_t) = \frac{1 \cdot \text{OBV}_{t-9} + 2 \cdot \text{OBV}_{t-8} + \dots + 9 \cdot \text{OBV}_{t-1} + 10 \cdot \text{OBV}_t}{55}$$

---

## 4. Cơ Chế Tương Tác Giữa Đường OBV Và MWA 10 Trong Thực Chiến VSA

| Trạng Thái Kỹ Thuật | Hành Vi Kỹ Thuật | Bản Chất Dòng Tiền (Smart Money) | Ứng Dụng Trong Hệ Thống VSA Đậu Mầm |
| :--- | :--- | :--- | :--- |
| **Giao Cắt Vàng (Golden Cross)** | Đường $\text{OBV}$ cắt dứt khoát từ dưới lên trên $\text{MWA}_{10}$ | Dòng tiền mua chủ động bùng nổ, xác nhận phe mua làm chủ hoàn toàn | **Kích hoạt Điểm Mua Đẩy Nền (Pocket Pivot)** hoặc xác nhận phiên Nổ Breakout an toàn |
| **Giao Cắt Tử Thần (Dead Cross)** | Đường $\text{OBV}$ cắt xuyên thủng xuống dưới $\text{MWA}_{10}$ | Lực cung áp đảo, tiền lớn ngừng gom hoặc bắt đầu tháo chạy | **Cảnh báo Bẫy Zero Đỉnh / Bulltrap / Sút**, kích hoạt quy tắc bảo toàn vốn |
| **OBV duy trì trên MWA 10** ($\text{OBV} > \text{MWA}_{10}$) | $\text{OBV}$ dốc lên và bám phía trên đường $\text{MWA}_{10}$ | Pha tích lũy gom hàng bền bỉ (Pha B / Pha D) | Giữ vị thế an tâm, đã có sự bảo kê của dòng tiền lớn |
| **OBV duy trì dưới MWA 10** ($\text{OBV} < \text{MWA}_{10}$) | $\text{OBV}$ dốc xuống và nằm dưới đường $\text{MWA}_{10}$ | Cạn kiệt dòng tiền hoặc đang bị xả hàng ngầm | Đứng ngoài quan sát, tuyệt đối không bắt đáy sớm |

---

## 5. Tín Hiệu Phân Kỳ VSA Đỉnh Cao

### 5.1. Phân Kỳ Dương (Bullish Divergence - Gom Hàng Đáy)
* **Hiện tượng**: Giá cổ phiếu đi ngang hoặc tạo đáy sau thấp hơn đáy trước, nhưng **đường OBV tạo đáy sau cao hơn đáy trước và cắt vọt lên trên MWA 10**.
* **Ý nghĩa VSA**: Phản ánh Smart Money đang âm thầm hấp thụ toàn bộ lực bán tháo của nhỏ lẻ ở vùng giá thấp (Spring / LPS / No Supply).
* **Hành động**: Mở **Điểm Cược 1/8 (Tầng 1 Zero-Loss)** ngay tại vùng kiệt cung.

### 5.2. Phân Kỳ Âm (Bearish Divergence - Phân Phối Đỉnh)
* **Hiện tượng**: Giá cổ phiếu rướn vượt đỉnh mới, nhưng **đường OBV không vượt đỉnh và cắt gãy xuống dưới MWA 10**.
* **Ý nghĩa VSA**: Dấu hiệu phân phối rõ rệt (Upthrust After Distribution - UTAD). Phe mua nhỏ lẻ đu bám ở giá cao trong khi tiền lớn âm thầm xả hàng.
* **Hành động**: Thoát hàng quyết liệt theo quy tắc Zero Đỉnh, không mua đuổi.

---

## 6. Đoạn Mã Python Chuẩn Hóa Sẵn Sàng Tích Hợp Hệ Thống

```python
import numpy as np
import pandas as pd

def calculate_obv_mwa10(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Tính toán chỉ báo OBV và đường làm mịn MWA 10 (Weighted Moving Average 10).
    Trả về: (OBV, MWA10, Tín_hiệu_Bullish_bool)
    """
    # 1. Hướng biến động giá (+1 nếu tăng, -1 nếu giảm, 0 nếu tham chiếu)
    direction = np.sign(df['close'].diff().fillna(0))
    
    # 2. Cộng dồn tích lũy khối lượng
    obv = (direction * df['volume']).cumsum()
    
    # 3. Tính đường làm mịn MWA 10 (WMA 10)
    weights = np.arange(1, 11)
    sum_weights = weights.sum() # = 55
    
    obv_mwa10 = obv.rolling(window=10).apply(
        lambda x: np.dot(x, weights) / sum_weights, raw=True
    )
    
    # 4. Trạng thái Bullish: OBV nằm trên MWA10
    is_bullish = obv > obv_mwa10
    
    return obv, obv_mwa10, is_bullish
```
