"""
bdi_momentum.py
HỆ THỐNG CHỈ BÁO XUNG LỰC BDI (BDI MOMENTUM INDICATOR - BMS)
Phiên bản: 1.0 (Lượng hóa 5 Thước đo Xung lực Tiền Bùng nổ & Backtest Engine)

Mục đích:
- Đo lường xung lực của cổ phiếu NGAY TẠI NỀN GIÁ (khi sắp tăng hoặc chớm nhú).
- Phân tách cổ phiếu có xung lực lò xo nén cực đại (Hạng A) với cổ phiếu yếu/dễ nổ xịt.
- Cung cấp mô-đun Backtest lượng hóa trong quá khứ để hiệu chỉnh dần các tham số.
"""

import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime

# Đảm bảo import được evaluator và dữ liệu chuẩn
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import evaluator
except ImportError:
    evaluator = None

# BẢNG THAM SỐ MẶC ĐỊNH (CÓ THỂ HIỆU CHỈNH DẦN KHI BACKTEST)
DEFAULT_PARAMS = {
    # 1. Trọng số 5 thước đo (Tổng = 100 điểm)
    "weight_rs": 25,      # Thước đo 1: Sức mạnh giá tương đối (RS vs VNI)
    "weight_vdu": 25,     # Thước đo 2: Bất đối xứng Khối lượng & Cạn cung
    "weight_vcp": 20,     # Thước đo 3: Độ nén lò xo VCP & Hội tụ MA
    "weight_smd": 15,     # Thước đo 4: Dòng tiền ngầm (OBV & MACD/RSI)
    "weight_pa": 15,      # Thước đo 5: Vị thế nến & Khớp lệnh vi mô

    # 2. Ngưỡng tham số đo lường
    "lookback_rs": 10,        # Số phiên đo RS so với VN-Index
    "vdu_dry_ratio": 0.65,    # Ngưỡng khối lượng cạn kiệt so với TB20 (<= 0.65x)
    "vol_up_down_ratio": 1.25,# Tỷ lệ Vol phiên tăng / Vol phiên giảm (>= 1.25x)
    "vcp_cr_threshold": 0.75, # Tỷ lệ co hẹp ATR5 / ATR20 (<= 0.75)
    "ma_conv_threshold": 2.0, # Độ lệch MA10/MA20 (<= 2.0%)
    "dist_ma20_min": -2.0,    # Khoảng cách tối thiểu tới MA20 (%)
    "dist_ma20_max": 3.8,     # Khoảng cách tối đa tới MA20 (%) - Tránh mua với
    "close_pos_min": 0.65,    # Vị thế đóng nến trong phiên (>= 65% thân trên)
}


def calculate_wma(series, length):
    """Tính đường trung bình có trọng số WMA."""
    weights = np.arange(1, length + 1)
    return series.rolling(length).apply(lambda w: np.dot(w, weights) / weights.sum(), raw=True)


def enrich_momentum_features(df, vni_df=None):
    """
    Tính toán và gắn các đặc trưng lượng hóa cần thiết cho 5 thước đo xung lực.
    """
    df = df.copy()
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'])
    
    # 1. ATR và Độ co hẹp biên độ
    high_low = df['high'] - df['low']
    high_prev_close = (df['high'] - df['close'].shift(1)).abs()
    low_prev_close = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    df['atr5'] = tr.rolling(5).mean()
    df['atr20'] = tr.rolling(20).mean()
    df['vcp_cr'] = df['atr5'] / (df['atr20'] + 1e-9)

    # Biên độ nền giá 20 phiên (Base Spread 20) & % Biến động
    high_20 = df['high'].rolling(20).max()
    low_20 = df['low'].rolling(20).min()
    df['base_spread_20'] = ((high_20 - low_20) / (low_20 + 1e-9)) * 100.0
    df['chg_pct'] = ((df['close'] - df['close'].shift(1)) / (df['close'].shift(1) + 1e-9)) * 100.0

    # 2. Đặc trưng Khối lượng & Cạn cung (VDU)
    if 'avg_vol20' not in df.columns:
        df['avg_vol20'] = df['volume'].rolling(20).mean()
    if 'avg_vol10' not in df.columns:
        df['avg_vol10'] = df['volume'].rolling(10).mean()
    df['vol_ratio_20'] = df['volume'] / (df['avg_vol20'] + 1e-9)
    df['vol_ratio_10'] = df['volume'] / (df['avg_vol10'] + 1e-9)
    
    # Tính tỷ lệ Vol phiên xanh vs Vol phiên đỏ trong 10 phiên
    is_up = df['close'] >= df['close'].shift(1)
    vol_up = df['volume'].where(is_up, 0.0)
    vol_down = df['volume'].where(~is_up, 0.0)
    sum_vol_up = vol_up.rolling(10, min_periods=2).sum()
    sum_vol_down = vol_down.rolling(10, min_periods=2).sum()
    df['vol_up_down_ratio'] = np.where(sum_vol_down > 0, sum_vol_up / (sum_vol_down + 1e-9), 2.5)
    df['vol_up_down_ratio'] = pd.Series(df['vol_up_down_ratio']).fillna(1.0)

    # 3. Độ hội tụ MA và Vị thế nến
    if 'ma10' not in df.columns:
        df['ma10'] = df['close'].rolling(10).mean()
    if 'ma20' not in df.columns:
        df['ma20'] = df['close'].rolling(20).mean()
    if 'ma50' not in df.columns:
        df['ma50'] = df['close'].rolling(50).mean()
        
    df['ma10_ma20_diff_pct'] = ((df['ma10'] - df['ma20']).abs() / (df['ma20'] + 1e-9)) * 100.0
    df['dist_ma20_pct'] = ((df['close'] - df['ma20']) / (df['ma20'] + 1e-9)) * 100.0
    
    # Vị thế đóng nến (Close Position 0.0 -> 1.0)
    candle_span = df['high'] - df['low']
    df['close_pos'] = np.where(candle_span > 1e-6, (df['close'] - df['low']) / candle_span, 0.5)

    # 4. Chỉ báo Dòng tiền ngầm OBV
    obv_change = np.where(df['close'] > df['close'].shift(1), df['volume'],
                 np.where(df['close'] < df['close'].shift(1), -df['volume'], 0.0))
    df['obv'] = obv_change.cumsum()
    df['obv_wma10'] = calculate_wma(df['obv'], 10)
    df['obv_bullish'] = df['obv'] >= df['obv_wma10']

    # MACD Histogram & RSI
    if 'macd' in df.columns and 'macd_signal' in df.columns:
        df['macd_hist'] = df['macd'] - df['macd_signal']
        df['macd_hist_slope'] = df['macd_hist'] - df['macd_hist'].shift(3)
    else:
        df['macd_hist'] = 0.0
        df['macd_hist_slope'] = 0.0

    # 5. Ghép nối dữ liệu VN-Index để đo RS (Relative Strength)
    if vni_df is not None and not vni_df.empty:
        vni_df = vni_df.copy()
        if 'time' in vni_df.columns:
            vni_df['time'] = pd.to_datetime(vni_df['time'])
        vni_sub = vni_df[['time', 'close']].rename(columns={'close': 'vni_close'})
        df = pd.merge(df, vni_sub, on='time', how='left')
        df['vni_close'] = df['vni_close'].ffill()
        
        # Ghép nối dữ liệu VN-Index để đo RS (Relative Strength)
        df['vni_close'] = df['vni_close'].ffill().bfill()
        
        # Lợi nhuận 10 phiên của Cổ phiếu vs VNINDEX
        df['ret_10_stock'] = (df['close'] - df['close'].shift(10)) / (df['close'].shift(10) + 1e-9) * 100.0
        df['ret_10_vni'] = (df['vni_close'] - df['vni_close'].shift(10)) / (df['vni_close'].shift(10) + 1e-9) * 100.0
        df['rs_alpha_10'] = (df['ret_10_stock'] - df['ret_10_vni']).fillna(0.0)
        
        # Downside Resilience (Số ngày VNI đỏ mà cổ phiếu giữ giá hoặc xanh)
        vni_down = df['vni_close'] < df['vni_close'].shift(1)
        stock_resilient = (df['close'] >= df['close'].shift(1)) & vni_down
        vni_down_sum = vni_down.rolling(10).sum()
        df['downside_resilience'] = np.where(vni_down_sum > 0, stock_resilient.rolling(10).sum() / (vni_down_sum + 1e-9), 0.5)
        df['downside_resilience'] = pd.Series(df['downside_resilience']).fillna(0.5).clip(0.0, 1.0)
    else:
        df['rs_alpha_10'] = 0.0
        df['downside_resilience'] = 0.5

    return df


def score_single_bar_momentum(row, params=DEFAULT_PARAMS):
    """
    Tính điểm Xung Lực BDI (BMS) cho một phiên cụ thể.
    Trả về:
    - total_score: 0 - 100
    - sub_scores: dict gồm 5 thước đo
    - details: diễn giải chi tiết từng thước đo
    """
    # -------------------------------------------------------------
    # THƯỚC ĐO 1: Sức Mạnh Giá Tương Đối (RS vs VN-Index) - Max: weight_rs
    # -------------------------------------------------------------
    max_rs = params["weight_rs"]
    rs_alpha = row.get("rs_alpha_10", 0.0)
    dr = row.get("downside_resilience", 0.5)
    
    # Điểm Alpha: Cổ phiếu khỏe hơn thị trường từ +2% đến +10%
    alpha_score = np.clip(12.5 + (rs_alpha * 1.25), 0.0, 15.0)
    # Điểm Kháng cự giảm (Downside Resilience): Giữ giá khi VNI đỏ
    dr_score = np.clip(dr * 10.0, 0.0, 10.0)
    score_rs = float(np.clip(alpha_score + dr_score, 0.0, max_rs))
    desc_rs = f"RS Alpha: {rs_alpha:+.1f}%, Kháng cự sụt giảm VNI: {dr*100:.0f}%"

    # -------------------------------------------------------------
    # THƯỚC ĐO 2: Bất Đối Xứng Khối Lượng & Cạn Cung (VDU) - Max: weight_vdu
    # -------------------------------------------------------------
    # THƯỚC ĐO 2: Động Lực Khối Lượng: Cạn Cung (VDU) HOẶC Khai Hỏa Đẩy Nền (Pocket Pivot) - Max: weight_vdu
    # -------------------------------------------------------------
    max_vdu = params["weight_vdu"]
    vol_r20 = row.get("vol_ratio_20", 1.0)
    vol_r10 = row.get("vol_ratio_10", 1.0)
    vol_up_down = row.get("vol_up_down_ratio", 1.0)
    chg = row.get("chg_pct", 0.0)
    c_pos = row.get("close_pos", 0.5)
    dist_ma20 = row.get("dist_ma20_pct", 0.0)
    
    # 2.1 Cạn cung (VDU) HOẶC Khai hỏa Pocket Pivot đẩy nền:
    # Cây đẩy nền Pocket Pivot: Giá tăng tốt (>= +0.8%), đóng nến cao (>= 65%), bám sát MA20 (<= 4.0%),
    # và Vol bắt đầu bung nở 1.25x - 2.8x TB20 ngay từ chân nền
    is_pocket_push = (chg >= 0.8) and (c_pos >= 0.65) and (1.25 <= vol_r20 <= 2.8) and (-2.0 <= dist_ma20 <= 4.2)
    
    if is_pocket_push:
        vdu_part = 15.0  # Điểm tối đa cho cây Khai hỏa Đẩy Nền (Pocket Pivot)
        desc_type = "Khai hỏa Pocket Pivot"
    elif vol_r20 <= params["vdu_dry_ratio"]:
        vdu_part = 15.0  # Kiệt vol sâu tại nền (Điểm Cược 1/8)
        desc_type = "Kiệt cung VDU"
    elif vol_r20 <= 0.85:
        vdu_part = 10.0  # Kiệt vol vừa
        desc_type = "Cạn cung vừa"
    elif vol_r20 <= 1.25:
        vdu_part = 6.0   # Bình thường
        desc_type = "Vol trung bình"
    else:
        vdu_part = 3.0   # Vol cao nhưng không đạt chuẩn đẩy nền
        desc_type = "Vol cao"
        
    # 2.2 Tỷ lệ Vol xanh vs Vol đỏ trong 10 phiên
    if vol_up_down >= 1.5:
        updown_part = 10.0
    elif vol_up_down >= params["vol_up_down_ratio"]:
        updown_part = 7.0
    elif vol_up_down >= 1.0:
        updown_part = 4.0
    else:
        updown_part = 1.0
        
    score_vdu = float(np.clip(vdu_part + updown_part, 0.0, max_vdu))
    desc_vdu = f"Vol/TB20: {vol_r20:.2f}x ({desc_type}), Tỷ lệ Vol Xanh/Đỏ: {vol_up_down:.2f}x"

    # -------------------------------------------------------------
    # THƯỚC ĐO 3: Độ Nén Lò Xo VCP & Hội Tụ MA - Max: weight_vcp
    # -------------------------------------------------------------
    max_vcp = params["weight_vcp"]
    vcp_cr = row.get("vcp_cr", 1.0)
    base_sp = row.get("base_spread_20", 15.0)
    ma_diff = row.get("ma10_ma20_diff_pct", 5.0)
    
    # 3.1 Co hẹp biến động ATR5/ATR20 (VCP) HOẶC Biên độ nền 20 phiên siết chặt (Base Spread <= 8%)
    if base_sp <= 8.0 or vcp_cr <= params["vcp_cr_threshold"]:
        vcp_part = 10.0  # Nền siết cực chặt (VCP loại A)
    elif base_sp <= 11.0 or vcp_cr <= 0.90:
        vcp_part = 7.0
    else:
        vcp_part = 3.0
        
    # 3.2 Độ hội tụ MA10 - MA20
    if ma_diff <= params["ma_conv_threshold"]:
        ma_part = 10.0  # Bện chặt xoắn cáp
    elif ma_diff <= 3.0:
        ma_part = 6.0
    else:
        ma_part = 2.0
        
    score_vcp = float(np.clip(vcp_part + ma_part, 0.0, max_vcp))
    desc_vcp = f"Nén VCP (ATR5/20): {vcp_cr:.2f}, Độ lệch MA10/20: {ma_diff:.2f}%"

    # -------------------------------------------------------------
    # THƯỚC ĐO 4: Dòng Tiền Ngầm (OBV & MACD/RSI) - Max: weight_smd
    # -------------------------------------------------------------
    max_smd = params["weight_smd"]
    obv_ok = bool(row.get("obv_bullish", False))
    hist_slope = row.get("macd_hist_slope", 0.0)
    rsi_val = row.get("rsi", 50.0)
    rsi_smooth = row.get("rsi_smoothed", 50.0)
    
    score_smd = 0.0
    if obv_ok:
        score_smd += 6.0  # OBV dốc lên trên WMA10
    if hist_slope >= 0.0:
        score_smd += 4.0  # MACD Histogram dốc lên
    if rsi_val >= 50.0 and rsi_val >= rsi_smooth:
        score_smd += 5.0  # RSI giữ nhịp trên 50 và trên đường smoothed
    elif rsi_val >= 48.0:
        score_smd += 2.0
    score_smd = float(np.clip(score_smd, 0.0, max_smd))
    desc_smd = f"OBV dốc lên: {'ĐẠT' if obv_ok else 'CHƯA'}, RSI: {rsi_val:.1f}, Hist Slope: {hist_slope:+.3f}"

    # -------------------------------------------------------------
    # THƯỚC ĐO 5: Vị Thế Nến & Khớp Lệnh Vi Mô - Max: weight_pa
    # -------------------------------------------------------------
    max_pa = params["weight_pa"]
    c_pos = row.get("close_pos", 0.5)
    dist_ma20 = row.get("dist_ma20_pct", 0.0)
    
    # 5.1 Vị thế đóng nến (Rút chân / Đóng sát đỉnh)
    if c_pos >= params["close_pos_min"]:
        pos_part = 8.0
    elif c_pos >= 0.50:
        pos_part = 5.0
    else:
        pos_part = 2.0
        
    # 5.2 Khoảng cách bám sát MA20 (Không mua với)
    if params["dist_ma20_min"] <= dist_ma20 <= params["dist_ma20_max"]:
        dist_part = 7.0  # Chân nền hoàn hảo
    elif dist_ma20 > params["dist_ma20_max"]:
        dist_part = 3.0  # Đã dướn xa nền MA20
    else:
        dist_part = 2.0  # Nằm quá sâu dưới MA20
        
    score_pa = float(np.clip(pos_part + dist_part, 0.0, max_pa))
    desc_pa = f"Vị thế đóng nến: {c_pos*100:.1f}%, Cách MA20: {dist_ma20:+.1f}%"

    # -------------------------------------------------------------
    # TỔNG HỢP VÀ XẾP HẠNG XUNG LỰC BDI (BMS)
    # -------------------------------------------------------------
    total_score = round(score_rs + score_vdu + score_vcp + score_smd + score_pa, 1)
    
    if total_score >= 80.0:
        tier = "HẠNG A (Lò Xo Nén Cực Đại - Sẵn Sàng Bùng Nổ)"
        badge = "🔥 SIÊU XUNG LỰC (HẠNG A)"
        action = "Ưu tiên giải ngân Điểm Cược 1/8 tại nền an toàn và đón đầu phiên Đẩy Nền/Pivot bứt phá (Tuyệt đối KHÔNG dùng Margin tại nền)."
    elif total_score >= 65.0:
        tier = "HẠNG B (Đang Tích Tụ Xung Lực Tốt)"
        badge = "⚡ XUNG LỰC KHÁ (HẠNG B)"
        action = "Đưa vào Tab Giám sát bám sát. Chờ phiên test cung cạn kiệt cuối cùng để mở mua."
    elif total_score >= 50.0:
        tier = "HẠNG C (Xung Lực Trung Bình / Giằng Co)"
        badge = "⚖️ XUNG LỰC TRUNG BÌNH (HẠNG C)"
        action = "Giằng co, chưa rõ xu hướng. Chỉ giải ngân tỷ trọng thăm dò rất nhỏ."
    else:
        tier = "HẠNG D (Xung Lực Yếu / Cung Lơ Lửng)"
        badge = "⚠️ XUNG LỰC YẾU (HẠNG D)"
        action = "Cung còn nhiều hoặc dễ nổ xịt (Bulltrap). Đứng ngoài quan sát."

    return {
        "bms_score": total_score,
        "tier": tier,
        "badge": badge,
        "action": action,
        "sub_scores": {
            "rs": round(score_rs, 1),
            "vdu": round(score_vdu, 1),
            "vcp": round(score_vcp, 1),
            "smd": round(score_smd, 1),
            "pa": round(score_pa, 1)
        },
        "details": {
            "rs": desc_rs,
            "vdu": desc_vdu,
            "vcp": desc_vcp,
            "smd": desc_smd,
            "pa": desc_pa
        }
    }


def calculate_bdi_momentum_series(symbol, df=None, vni_df=None, params=DEFAULT_PARAMS):
    """
    Tính chuỗi điểm xung lực BDI (BMS) cho toàn bộ lịch sử dữ liệu của một cổ phiếu.
    """
    if df is None:
        if evaluator is None:
            raise ValueError("Không tìm thấy mô-đun evaluator để lấy dữ liệu!")
        df = evaluator.get_prepared_stock_df(symbol)
    if vni_df is None and evaluator is not None:
        vni_df = evaluator.get_prepared_stock_df("VNINDEX")
        
    enriched = enrich_momentum_features(df, vni_df)
    
    scores = []
    tiers = []
    rs_list, vdu_list, vcp_list, smd_list, pa_list = [], [], [], [], []
    
    for _, row in enriched.iterrows():
        res = score_single_bar_momentum(row, params)
        scores.append(res["bms_score"])
        tiers.append(res["tier"])
        rs_list.append(res["sub_scores"]["rs"])
        vdu_list.append(res["sub_scores"]["vdu"])
        vcp_list.append(res["sub_scores"]["vcp"])
        smd_list.append(res["sub_scores"]["smd"])
        pa_list.append(res["sub_scores"]["pa"])
        
    enriched['bms_score'] = scores
    enriched['bms_tier'] = tiers
    enriched['bms_rs'] = rs_list
    enriched['bms_vdu'] = vdu_list
    enriched['bms_vcp'] = vcp_list
    enriched['bms_smd'] = smd_list
    enriched['bms_pa'] = pa_list
    
    return enriched


def backtest_bdi_momentum(symbol, start_date=None, end_date=None, threshold=75.0, 
                           forward_windows=[5, 10, 20], params=DEFAULT_PARAMS):
    """
    HÀM BACKTEST LƯỢNG HÓA CHỈ BÁO XUNG LỰC BDI:
    - Tìm tất cả các phiên trong quá khứ có BMS >= threshold.
    - Đo lường lợi nhuận thực tế sau T+5, T+10, T+20 phiên.
    - Tính toán Winrate, Lợi nhuận trung bình, Max Runup (Lãi lớn nhất) và Drawdown.
    """
    df = calculate_bdi_momentum_series(symbol, params=params)
    if start_date:
        df = df[df['time'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['time'] <= pd.to_datetime(end_date)]
        
    df = df.reset_index(drop=True)
    n = len(df)
    signals = []
    
    for i in range(n - max(forward_windows)):
        score = df.loc[i, 'bms_score']
        if score >= threshold:
            entry_price = df.loc[i, 'close']
            entry_date = df.loc[i, 'time'].strftime('%Y-%m-%d')
            
            sig = {
                "date": entry_date,
                "score": score,
                "entry_price": entry_price,
            }
            
            for w in forward_windows:
                exit_price = df.loc[i + w, 'close']
                ret = (exit_price - entry_price) / entry_price * 100.0
                
                # Tính max lãi và max lỗ trong khoảng forward w phiên
                sub_period = df.loc[i+1 : i+w]
                max_high = sub_period['high'].max()
                min_low = sub_period['low'].min()
                max_gain = (max_high - entry_price) / entry_price * 100.0
                max_dd = (min_low - entry_price) / entry_price * 100.0
                
                sig[f"ret_T{w}"] = ret
                sig[f"max_gain_T{w}"] = max_gain
                sig[f"max_dd_T{w}"] = max_dd
                
            signals.append(sig)
            
    if not signals:
        return {
            "symbol": symbol,
            "threshold": threshold,
            "total_signals": 0,
            "message": "Không tìm thấy phiên nào đạt ngưỡng BMS trong khoảng thời gian đã chọn."
        }
        
    sig_df = pd.DataFrame(signals)
    summary = {
        "symbol": symbol,
        "threshold": threshold,
        "total_signals": len(sig_df),
        "windows": {}
    }
    
    for w in forward_windows:
        rets = sig_df[f"ret_T{w}"]
        gains = sig_df[f"max_gain_T{w}"]
        dds = sig_df[f"max_dd_T{w}"]
        
        summary["windows"][f"T+{w}"] = {
            "win_rate_pct": round((rets > 0).mean() * 100.0, 1),
            "avg_return_pct": round(rets.mean(), 2),
            "median_return_pct": round(rets.median(), 2),
            "avg_max_gain_pct": round(gains.mean(), 2),
            "avg_max_drawdown_pct": round(dds.mean(), 2),
            "profit_factor": round(abs(rets[rets > 0].sum() / (rets[rets < 0].sum() + 1e-9)), 2)
        }
        
    return {
        "summary": summary,
        "sample_signals": signals[-10:]  # Trả về 10 tín hiệu gần nhất làm mẫu
    }


def get_latest_bms_momentum(symbol, df=None, vni_df=None, params=DEFAULT_PARAMS, force_reload=True):
    """
    Tính nhanh điểm Xung Lực BMS cho phiên mới nhất của một cổ phiếu.
    Trả về dict chuẩn để gửi cảnh báo Telegram.
    force_reload=True đảm bảo luôn đọc dữ liệu tươi mới nhất từ đĩa/nguồn cấp thay vì dùng RAM cache cũ.
    """
    try:
        if df is None:
            if evaluator is None:
                return {"status": "error", "message": "Evaluator not found"}
            df = evaluator.get_prepared_stock_df(symbol, force_reload=force_reload)
        if df is None or df.empty:
            return {"status": "error", "message": f"Không có dữ liệu cho {symbol}"}
        if vni_df is None and evaluator is not None:
            vni_df = evaluator.get_prepared_stock_df("VNINDEX", force_reload=force_reload)
            
        enriched = enrich_momentum_features(df, vni_df)
        latest = enriched.iloc[-1]
        score_info = score_single_bar_momentum(latest, params)
        
        return {
            "status": "success",
            "symbol": symbol.upper(),
            "date": latest['time'].strftime('%d/%m/%Y') if 'time' in latest else '',
            "close": float(latest['close']),
            "chg_pct": float(latest.get('chg_pct', 0.0)),
            "volume": int(latest['volume']),
            "avg_vol20": float(latest.get('avg_vol20', 1.0)),
            "vol_ratio_20": float(latest.get('vol_ratio_20', 1.0)),
            "bms_score": score_info["bms_score"],
            "tier": score_info["tier"],
            "badge": score_info["badge"],
            "action": score_info["action"],
            "sub_scores": score_info["sub_scores"],
            "details": score_info["details"]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    print("=== KIỂM THỬ CHỈ BÁO XUNG LỰC BDI TRÊN MỘT SỐ CỔ PHIẾU TIÊU BIỂU ===")
    
    test_symbols = ["TNG", "MSB", "FPT"]
    for sym in test_symbols:
        df_sym = calculate_bdi_momentum_series(sym)
        latest = df_sym.iloc[-1]
        res = score_single_bar_momentum(latest)
        print(f"\n[{sym}] Ngày {latest['time'].strftime('%Y-%m-%d')} - Giá: {latest['close']:.2f}")
        print(f"-> ĐIỂM XUNG LỰC BDI (BMS): {res['bms_score']}/100 | {res['badge']}")
        print(f"   Hành động: {res['action']}")
        print(f"   Chi tiết: RS={res['sub_scores']['rs']}đ | VDU={res['sub_scores']['vdu']}đ | VCP={res['sub_scores']['vcp']}đ | SMD={res['sub_scores']['smd']}đ | PA={res['sub_scores']['pa']}đ")
