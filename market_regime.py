"""
market_regime.py
MÔ-ĐUN LƯỢNG HÓA BỐI CẢNH THỊ TRƯỜNG & ĐẾM PHIÊN PHÂN PHỐI VN-INDEX
Phiên bản: 1.0

Chức năng:
- Đếm số phiên phân phối (Distribution Days) của chỉ số VN-Index trong 25 phiên giao dịch gần nhất.
- Phân loại trạng thái Đèn Giao Thông: XANH (0-2 phiên), VÀNG (3 phiên), CAM (4 phiên), ĐỎ (>= 5 phiên).
- Trả về dòng trạng thái Footer chuẩn hóa ở cuối mỗi báo cáo Telegram.
- NGUYÊN TẮC: Hoàn toàn ĐỘC LẬP, KHÔNG can thiệp/làm thay đổi cách chấm điểm VSA, BDI, BMS hay các điểm mua.
"""

import os
import sys
import pandas as pd
import numpy as np

# Cache kết quả trong 60 giây để tránh tính toán lặp lại liên tục
_MARKET_REGIME_CACHE = {
    "timestamp": 0,
    "result": None
}

def analyze_market_regime(lookback: int = 25, force_refresh: bool = False) -> dict:
    """
    Phân tích số phiên phân phối của VN-Index trong `lookback` phiên (mặc định 25 phiên).
    """
    import time
    now_ts = time.time()
    global _MARKET_REGIME_CACHE
    
    if not force_refresh and _MARKET_REGIME_CACHE["result"] is not None and (now_ts - _MARKET_REGIME_CACHE["timestamp"] < 60):
        return _MARKET_REGIME_CACHE["result"]
        
    try:
        import evaluator
        vni_df = evaluator.get_prepared_stock_df("VNINDEX", force_reload=force_refresh)
        if vni_df is None or vni_df.empty or len(vni_df) < 30:
            return _default_market_regime_fallback()
            
        df = vni_df.copy()
        df['chg_pct'] = (df['close'] - df['close'].shift(1)) / df['close'].shift(1) * 100.0
        df['close_pos'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-9)
        if 'avg_vol20' not in df.columns:
            df['avg_vol20'] = df['volume'].rolling(20).mean()
            
        recent = df.iloc[-lookback:].copy()
        dist_days = []
        
        for i in range(len(recent)):
            idx = recent.index[i]
            row = recent.iloc[i]
            prev_idx = idx - 1
            prev_row = df.loc[prev_idx] if prev_idx in df.index else row
            
            is_dist = False
            dist_type = ""
            
            # 1. Classic Selling Day: Giảm >= 0.2%, Vol > Vol trước (hoặc >= 1.15x TB20), nến đóng nửa dưới
            if row['chg_pct'] <= -0.2 and (row['volume'] > prev_row['volume'] or row['volume'] >= 1.15 * row['avg_vol20']) and row['close_pos'] <= 0.50:
                is_dist = True
                dist_type = f"Classic Selling ({row['chg_pct']:+.2f}%, Vol > Vol trước)"
                
            # 2. Churning Day: Nỗ lực vs Kết quả (Biên độ -0.15% đến +0.25%, nhưng Vol >= 1.25x TB20 và Vol > Vol trước)
            elif -0.15 <= row['chg_pct'] <= 0.25 and (row['volume'] > prev_row['volume'] and row['volume'] >= 1.25 * row['avg_vol20']) and row['close_pos'] <= 0.60:
                is_dist = True
                dist_type = f"Churning Day (Xả phiên đi ngang, Vol={row['volume']/row['avg_vol20']:.2f}x TB20)"
                
            # 3. Upthrust Bar / Bẫy đỉnh: Vượt đỉnh phiên trước nhưng rụt đầu, đóng nến 35% thân dưới, Vol cao
            elif row['high'] > prev_row['high'] and row['close'] < row['open'] and row['close_pos'] <= 0.35 and row['volume'] > prev_row['volume']:
                is_dist = True
                dist_type = f"Upthrust Bar (Râu trên dài, Vol cao)"
                
            if is_dist:
                # Kiểm tra vô hiệu hóa nếu sau phiên này chỉ số vượt đỉnh +5%
                later_bars = recent.iloc[i+1:]
                is_expired = False
                if not later_bars.empty:
                    max_later_close = later_bars['close'].max()
                    if max_later_close > row['high'] * 1.05:
                        is_expired = True
                        
                if not is_expired:
                    dist_days.append({
                        "date": str(row['time'])[:10],
                        "close": float(row['close']),
                        "chg_pct": float(row['chg_pct']),
                        "volume": float(row['volume']),
                        "vol_ratio": float(row['volume'] / (row['avg_vol20'] + 1e-9)),
                        "type": dist_type
                    })
                    
        count = len(dist_days)
        
        # Đánh giá cấp độ Đèn Giao Thông
        if count <= 2:
            color = "XANH"
            icon = "🟢"
            status_text = "Thị trường an toàn, áp lực bán phân phối thấp"
        elif count == 3:
            color = "VÀNG"
            icon = "🟡"
            status_text = "Cảnh giác nhẹ, xuất hiện áp lực cung chốt lời"
        elif count == 4:
            color = "CAM"
            icon = "🟠"
            status_text = "Áp lực phân phối gia tăng rõ rệt"
        else: # count >= 5
            color = "ĐỎ"
            icon = "🔴"
            status_text = "Cảnh báo phân phối mức cao, rủi ro điều chỉnh lớn"
            
        latest_bar = recent.iloc[-1]
        footer_text = f"🚦 <b>Bối cảnh Thị trường (VN-Index):</b> {icon} <b>{color}</b> [{count}/{lookback} phiên phân phối] – <i>{status_text}</i>"
        
        result = {
            "status": "success",
            "count": count,
            "lookback": lookback,
            "color": color,
            "icon": icon,
            "status_text": status_text,
            "footer_text": footer_text,
            "dist_days": dist_days,
            "latest_close": float(latest_bar['close']),
            "latest_date": str(latest_bar['time'])[:10]
        }
        
        _MARKET_REGIME_CACHE["timestamp"] = now_ts
        _MARKET_REGIME_CACHE["result"] = result
        return result
        
    except Exception as e:
        return _default_market_regime_fallback(str(e))

def _default_market_regime_fallback(err_msg: str = "") -> dict:
    return {
        "status": "error",
        "count": 0,
        "lookback": 25,
        "color": "XANH",
        "icon": "🟢",
        "status_text": "Chưa có dữ liệu cập nhật",
        "footer_text": "🚦 <b>Bối cảnh Thị trường (VN-Index):</b> 🟢 <b>XANH</b> [0/25 phiên phân phối] – <i>Theo dõi biến động thị trường</i>",
        "dist_days": [],
        "latest_close": 0.0,
        "latest_date": ""
    }

def get_market_regime_footer_line() -> str:
    """Trả về duy nhất 1 dòng text footer chuẩn hóa để nhúng vào cuối các báo cáo."""
    info = analyze_market_regime()
    return info.get("footer_text", "")
