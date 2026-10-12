"""
no2_engine.py
CHIẾN LƯỢC SĂN SIÊU CỔ PHIẾU NỀN SỐ 2 TRÊN CAO (STRATEGY No2)
Phiên bản: 1.0 (Quy chuẩn 6 Tầng Định Lượng & Machine Learning Pattern Extractor)

Triết lý cốt lõi:
- Săn lùng siêu cổ phiếu KHI ĐANG NẰM TRONG NỀN SỐ 2 (chưa xuất hiện điểm nổ).
- Lấy vị thế chủ động tại các phiên kiệt cung (Test Cung / No Supply / Pocket Pivot sớm),
  không chờ Breakout để tránh bị trượt giá hoặc bỏ lỡ siêu sóng chạy nước rút.
- Loại bỏ ràng buộc đỉnh 52 tuần để bắt trọn các siêu cổ phiếu đi lên từ chân sóng chu kỳ lớn (như DIG, CEO, VIX, HAH, VOS, NKG, HSG).
"""

import os
import sys
import numpy as np
import pandas as pd

# Add root directory to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import bdi_momentum
from bdi_momentum import DEFAULT_PARAMS, enrich_momentum_features, score_single_bar_momentum
import evaluator
from evaluator import calculate_rsi, calculate_macd

def detect_no2_in_df(df: pd.DataFrame, vni_df: pd.DataFrame = None, target_idx: int = None) -> dict:
    """
    Kiểm tra một mốc thời gian (hoặc phiên gần nhất) của cổ phiếu có đạt tiêu chuẩn Chiến Lược No2 hay không.
    Trả về:
    - is_no2: True/False
    - no2_score: 0 - 100 điểm
    - status: 'IN_BASE_C1' | 'POCKET_LAUNCH_P1' | 'BREAKOUT_STAGE' | 'NOT_MET'
    - pillars: Kết quả chi tiết 6 Tầng
    - metrics: Các chỉ số lượng hóa
    """
    n = len(df)
    if n < 80:
        return {"is_no2": False, "reason": "Lịch sử dữ liệu quá ngắn (<80 phiên)"}
        
    idx = (n - 1) if target_idx is None else target_idx
    if idx < 60:
        return {"is_no2": False, "reason": "Vị trí kiểm tra quá gần đầu chuỗi"}
        
    closes = df['close'].values
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    vols = df['volume'].values
    dates = df['time'].values
    
    # -------------------------------------------------------------
    # TẦNG 1: DẤU VẾT NHỊP TĂNG 1 (Stage 1 Markup Footprint)
    # -------------------------------------------------------------
    # Kiểm tra trong cửa sổ [idx - 80, idx - 15] có nhịp tăng từ +25% đến +65%
    lookback_start = max(0, idx - 85)
    lookback_mid = max(lookback_start + 15, idx - 15)
    
    # Tìm đáy của Nền 1
    slice_pre = closes[lookback_start:lookback_mid]
    if len(slice_pre) < 15:
        return {"is_no2": False, "reason": "Không đủ dữ liệu quá khứ cho Nền 1"}
        
    min_idx_rel = np.argmin(slice_pre)
    base1_low = slice_pre[min_idx_rel]
    
    # Tìm đỉnh của Nhịp tăng 1
    slice_peak = closes[lookback_start + min_idx_rel : idx - 8]
    if len(slice_peak) < 5:
        stage1_peak = np.max(slice_pre)
    else:
        stage1_peak = np.max(slice_peak)
        
    stage1_gain = ((stage1_peak - base1_low) / (base1_low + 1e-9)) * 100.0
    pass_t1 = bool(22.0 <= stage1_gain <= 85.0)
    desc_t1 = f"Nhịp tăng 1: +{stage1_gain:.1f}% (từ {base1_low:.2f} lên {stage1_peak:.2f})"
    
    # -------------------------------------------------------------
    # TẦNG 2: BẺ CONG XU HƯỚNG TRUNG - DÀI HẠN (Trend Inflection)
    # Bỏ tiêu chí cách đỉnh 52 tuần. Chỉ yêu cầu Close >= MA50, Close >= MA100, MA20 >= MA50
    # -------------------------------------------------------------
    c_close = closes[idx]
    ma20 = np.mean(closes[max(0, idx-20):idx+1])
    ma50 = np.mean(closes[max(0, idx-50):idx+1])
    ma100 = np.mean(closes[max(0, idx-100):idx+1]) if idx >= 100 else ma50
    ma50_prev = np.mean(closes[max(0, idx-55):idx-4]) if idx >= 55 else ma50
    ma50_slope = (ma50 - ma50_prev) / (ma50_prev + 1e-9) * 100.0
    
    pass_t2 = bool(c_close >= ma50 * 0.97 and c_close >= ma100 * 0.95 and ma20 >= ma50 * 0.97 and ma50_slope >= -0.5)
    desc_t2 = f"Giá ({c_close:.2f}) >= MA50 ({ma50:.2f}) & MA100 ({ma100:.2f}), MA20 ({ma20:.2f}) >= MA50"
    
    # -------------------------------------------------------------
    # TẦNG 3: CẤU TRÚC ĐỘ NÉN NỀN SỐ 2 (Base Architecture VCP Pro)
    # Thời gian: 2 đến 8 tuần (10 - 40 phiên). Độ sâu điều chỉnh <= 15%
    # -------------------------------------------------------------
    # Xác định độ dài Nền 2: tính từ đỉnh nhịp 1 đến idx
    peak_abs_idx = lookback_start + min_idx_rel + np.argmax(slice_peak) if len(slice_peak) > 0 else (idx - 15)
    base2_duration = max(8, idx - peak_abs_idx)
    
    # Giới hạn phân tích nền trong 10 đến 40 phiên gần nhất
    base2_slice_len = min(idx, max(10, min(40, base2_duration)))
    base2_closes = closes[idx - base2_slice_len : idx + 1]
    base2_highs = highs[idx - base2_slice_len : idx + 1]
    base2_lows = lows[idx - base2_slice_len : idx + 1]
    
    base2_high = np.max(base2_highs)
    base2_low = np.min(base2_lows)
    base2_depth = ((base2_high - base2_low) / (base2_high + 1e-9)) * 100.0
    
    # ATR contraction
    tr = np.maximum(highs[idx-20:idx+1] - lows[idx-20:idx+1], 
                    np.abs(highs[idx-20:idx+1] - np.roll(closes[idx-20:idx+1], 1)))[1:]
    atr5 = np.mean(tr[-5:]) if len(tr) >= 5 else 1.0
    atr20 = np.mean(tr) if len(tr) >= 20 else atr5
    vcp_ratio = atr5 / (atr20 + 1e-9)
    
    pass_t3 = bool(8 <= base2_duration <= 45 and base2_depth <= 16.5 and (vcp_ratio <= 0.85 or base2_depth <= 10.0))
    desc_t3 = f"Nền 2 kéo dài {base2_duration} phiên, độ sâu điều chỉnh: {base2_depth:.1f}%, ATR5/20: {vcp_ratio:.2f}"
    
    # -------------------------------------------------------------
    # TẦNG 4: THANH KHOẢN VSA TRONG NỀN (Volume Dry-Up - Cạn Cung Sâu)
    # Khối lượng cạn kiệt <= 0.5x TB20, xuất hiện No Supply / Test Cung
    # -------------------------------------------------------------
    avg_vol20 = np.mean(vols[max(0, idx-20):idx+1])
    base2_vols = vols[idx - base2_slice_len : idx + 1]
    min_vol_base2 = np.min(base2_vols)
    min_vol_ratio = min_vol_base2 / (avg_vol20 + 1e-9)
    curr_vol_ratio = vols[idx] / (avg_vol20 + 1e-9)
    
    # Kiểm tra nến Test Cung hoặc No Supply trong 5 phiên gần nhất
    has_test_cung = False
    has_no_supply = False
    for lb in range(max(0, idx - 5), idx + 1):
        c_p = closes[lb]
        op_p = opens[lb]
        hi_p = highs[lb]
        lo_p = lows[lb]
        v_p = vols[lb]
        v_r = v_p / (avg_vol20 + 1e-9)
        c_len = hi_p - lo_p
        c_pos = (c_p - lo_p) / (c_len + 1e-9) if c_len > 0 else 0.5
        
        # Test Cung: nhúng xuống rút chân, vol kiệt <= 0.75x
        if c_pos >= 0.55 and v_r <= 0.75 and lo_p <= ma20 * 1.01:
            has_test_cung = True
        # No Supply: nến giảm hẹp, vol <= 0.60x
        if c_p <= op_p and (hi_p - lo_p) / (c_p + 1e-9) <= 0.025 and v_r <= 0.65:
            has_no_supply = True
            
    pass_t4 = bool(min_vol_ratio <= 0.55 or (curr_vol_ratio <= 0.70 and (has_test_cung or has_no_supply)))
    desc_t4 = f"Đáy kiệt vol Nền 2: {min_vol_ratio:.2f}x TB20 | Test Cung: {'CÓ' if has_test_cung else 'CHƯA'} | No Supply: {'CÓ' if has_no_supply else 'CHƯA'}"
    
    # -------------------------------------------------------------
    # TẦNG 5: DÒNG TIỀN NGẦM & SỨC MẠNH TƯƠNG ĐỐI (OBV & RS Resilience)
    # -------------------------------------------------------------
    # OBV calculation
    close_diff = np.diff(closes)
    dir_arr = np.zeros(len(closes))
    dir_arr[1:][close_diff > 0] = 1.0
    dir_arr[1:][close_diff < 0] = -1.0
    obv_arr = np.cumsum(dir_arr * vols)
    
    w10 = np.arange(1, 11)
    obv_wma10_val = np.dot(obv_arr[idx-9:idx+1], w10) / w10.sum() if idx >= 9 else obv_arr[idx]
    pass_obv = bool(obv_arr[idx] >= obv_wma10_val * 0.99)
    
    # Downside Resilience vs VNI
    rs_score = 15.0
    if vni_df is not None and not vni_df.empty:
        # Merge time
        vni_closes = vni_df['close'].values
        if len(vni_closes) >= 10:
            ret_stock_10 = (closes[idx] - closes[idx-10]) / (closes[idx-10] + 1e-9) * 100.0
            ret_vni_10 = (vni_closes[-1] - vni_closes[-10]) / (vni_closes[-10] + 1e-9) * 100.0
            rs_alpha = ret_stock_10 - ret_vni_10
            rs_score = np.clip(12.5 + (rs_alpha * 1.25), 0.0, 25.0)
            
    pass_t5 = pass_obv
    desc_t5 = f"OBV dốc lên trên WMA10: {'ĐẠT' if pass_obv else 'CHƯA'} | RS Điểm: {rs_score:.1f}/25"
    
    # -------------------------------------------------------------
    # TẦNG 6: ĐIỂM BẤM CÒ CHỦ ĐỘNG TRONG NỀN (Pre-emptive Positioning Trigger)
    # -------------------------------------------------------------
    # Lấy điểm BMS (ưu tiên từ cột đã precompute để chạy siêu tốc)
    if 'bms_score' in df.columns:
        bms_val = float(df['bms_score'].iloc[idx])
        bms_tier = str(df['bms_tier'].iloc[idx]) if 'bms_tier' in df.columns else "HẠNG B"
    else:
        df_single = df.iloc[max(0, idx-35):idx+1].copy()
        df_single['rsi'] = calculate_rsi(df_single, period=14)
        df_single['rsi_smoothed'] = df_single['rsi'].ewm(span=9, adjust=False).mean()
        m_line, s_line, _ = calculate_macd(df_single)
        df_single['macd'] = m_line
        df_single['macd_signal'] = s_line
        enriched = enrich_momentum_features(df_single, vni_df)
        last_row = enriched.iloc[-1]
        bms_res = score_single_bar_momentum(last_row, DEFAULT_PARAMS)
        bms_val = bms_res['bms_score']
        bms_tier = bms_res['tier']

    # Trạng thái hành động:
    # 1. Pocket Pivot Launch (P1 sớm): chớm nhú từ chân nền với vol nở nhẹ, tăng >= 1.2%
    c_chg = ((c_close - closes[idx-1]) / (closes[idx-1] + 1e-9)) * 100.0
    c_pos_now = (c_close - lows[idx]) / (highs[idx] - lows[idx] + 1e-9) if (highs[idx] > lows[idx]) else 0.5
    
    is_pocket_launch = (c_chg >= 1.2) and (curr_vol_ratio >= 1.15) and (c_pos_now >= 0.65) and (c_close >= ma20)
    is_in_base_c1 = (curr_vol_ratio <= 0.85) and (abs(c_close - ma20) / ma20 <= 0.03) and (has_test_cung or has_no_supply or bms_val >= 60.0)
    is_breakout = (c_close >= base2_high * 0.99) and (curr_vol_ratio >= 1.4) and (c_chg >= 2.5)
    
    if is_breakout:
        action_status = "BREAKOUT_STAGE (Vừa Bứt Phá Nền 2 - Chạy Nước Rút)"
        action_code = "B1"
    elif is_pocket_launch:
        action_status = "POCKET_LAUNCH_P1 (Chớm Nhú Pocket Pivot Từ Chân Nền - Gia Tăng Ngay)"
        action_code = "P1"
    elif is_in_base_c1 or pass_t4:
        action_status = "IN_BASE_C1 (Đang Nén Chặt Trong Nền 2 - Mở Cược 1/8 Chủ Động)"
        action_code = "C1"
    else:
        action_status = "MONITORING (Đang Tích Lũy Nền 2 - Quan Sát Test Cung)"
        action_code = "WATCH"
        
    # Tính điểm No2 tổng hợp (0 - 100 điểm)
    pillar_scores = {
        "p1_stage1_gain": 20.0 if pass_t1 else 5.0,
        "p2_trend_inflection": 20.0 if pass_t2 else 0.0,
        "p3_base2_vcp": 20.0 if pass_t3 else 5.0,
        "p4_vsa_vdu": 20.0 if pass_t4 else 5.0,
        "p5_smd_obv": 10.0 if pass_t5 else 0.0,
        "p6_bms_trigger": min(10.0, max(0.0, (bms_val - 50.0) / 3.0))
    }
    no2_total_score = round(sum(pillar_scores.values()), 1)
    
    # Kết luận No2: Đạt khi điểm tổng >= 70 và vượt qua Tầng 1, Tầng 2, Tầng 3, Tầng 4
    is_no2_qualified = bool(no2_total_score >= 68.0 and pass_t1 and pass_t2 and (pass_t3 or pass_t4))
    
    return {
        "symbol": df['symbol'].iloc[0] if 'symbol' in df.columns else "UNKNOWN",
        "date": str(dates[idx])[:10],
        "is_no2": is_no2_qualified,
        "no2_score": no2_total_score,
        "action_code": action_code,
        "action_status": action_status,
        "bms_score": bms_val,
        "bms_tier": bms_tier,
        "stage1_gain_pct": round(stage1_gain, 1),
        "base2_duration_days": int(base2_duration),
        "base2_depth_pct": round(base2_depth, 1),
        "min_vol_ratio_base2": round(min_vol_ratio, 2),
        "curr_vol_ratio": round(curr_vol_ratio, 2),
        "vcp_ratio": round(vcp_ratio, 2),
        "close": round(c_close, 2),
        "ma20": round(ma20, 2),
        "ma50": round(ma50, 2),
        "ma100": round(ma100, 2),
        "pillars": {
            "t1_stage1": {"passed": pass_t1, "desc": desc_t1, "score": pillar_scores["p1_stage1_gain"]},
            "t2_trend_inflection": {"passed": pass_t2, "desc": desc_t2, "score": pillar_scores["p2_trend_inflection"]},
            "t3_base2_vcp": {"passed": pass_t3, "desc": desc_t3, "score": pillar_scores["p3_base2_vcp"]},
            "t4_vsa_vdu": {"passed": pass_t4, "desc": desc_t4, "score": pillar_scores["p4_vsa_vdu"]},
            "t5_smd_obv": {"passed": pass_t5, "desc": desc_t5, "score": pillar_scores["p5_smd_obv"]},
            "t6_bms_trigger": {"passed": bms_val >= 60.0, "desc": f"BMS: {bms_val:.1f} điểm ({bms_tier})", "score": pillar_scores["p6_bms_trigger"]}
        },
        "capital_plan": {
            "entry_c1": "Mở cược vị thế 1 (1/8 - 1/4 NAV) ngay trong nền khi VSA kiệt vol ≤ 0.5x hoặc nến Test Cung/No Supply.",
            "entry_p1": "Gia tăng vị thế 2 (thêm 1/4 NAV) khi xuất hiện Pocket Pivot nhú từ chân nền với vol nở nhẹ ≥ 1.2x.",
            "entry_b1": "Đánh đủ 100% tỷ trọng hoặc mở Margin khi Breakout dứt khoát vượt đỉnh Nền 2 với vol bùng nổ ≥ 1.5x.",
            "stop_loss": f"Kỷ luật cắt lỗ khi thủng biên dưới Nền 2 hoặc gãy MA20 (vùng {ma20 * 0.96:.2f} - {ma20 * 0.98:.2f}, lỗ tối đa 4-5%).",
            "target": f"Mục tiêu siêu sóng nhịp 2: +35% đến +60% (vùng {c_close * 1.35:.2f} - {c_close * 1.60:.2f}).",
            "margin_trigger": "Kích hoạt Margin khi vị thế C1 & P1 đã có sẵn đệm lãi ≥ +7% và cổ phiếu bứt phá Nền 2."
        }
    }


def load_stock_dat_df(symbol: str) -> pd.DataFrame:
    """Đọc dữ liệu nhị phân siêu tốc từ AmiBroker/Metakit hoặc fallback sang vnstock/CSV."""
    import struct
    clean_sym = symbol.strip().upper()
    metakit_paths = [
        os.path.join(r"C:\MetakitData\AmiBroker\EOD\stock", f"{clean_sym}.dat"),
        os.path.join(r"D:\MetakitData\AmiBroker\EOD\stock", f"{clean_sym}.dat"),
        os.path.join(r"E:\MetakitData\AmiBroker\EOD\stock", f"{clean_sym}.dat"),
        os.path.join(r"C:\MetakitData\AmiBroker\EOD\index", f"{clean_sym}.dat"),
        os.path.join(r"D:\MetakitData\AmiBroker\EOD\index", f"{clean_sym}.dat"),
    ]
    file_path = None
    for p in metakit_paths:
        if os.path.exists(p):
            file_path = p
            break

    if file_path:
        try:
            with open(file_path, "rb") as f:
                header = f.read(32)
                if len(header) >= 32:
                    num_recs = struct.unpack("<I", header[:4])[0]
                    if num_recs > 0:
                        dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
                        for _ in range(num_recs):
                            rec = f.read(32)
                            if len(rec) < 32:
                                break
                            date_int, pad, open_p, high_p, low_p, close_p, vol, val = struct.unpack("<IIfffffI", rec)
                            if date_int < 20070101:
                                continue
                            year = date_int // 10000
                            month = (date_int % 10000) // 100
                            day = date_int % 100
                            if year < 2007 or year > 2030 or month < 1 or month > 12 or day < 1 or day > 31:
                                continue
                            if open_p <= 0 or high_p <= 0 or low_p <= 0 or close_p <= 0:
                                continue
                            dates.append(f"{year:04d}-{month:02d}-{day:02d}")
                            opens.append(float(open_p))
                            highs.append(float(high_p))
                            lows.append(float(low_p))
                            closes.append(float(close_p))
                            volumes.append(float(vol))
                        if dates:
                            return pd.DataFrame({
                                "time": dates,
                                "symbol": clean_sym,
                                "open": opens,
                                "high": highs,
                                "low": lows,
                                "close": closes,
                                "volume": volumes
                            })
        except Exception:
            pass

    # Fallback nguồn dữ liệu qua evaluator (vnstock hoặc CSV nội bộ)
    try:
        if evaluator and hasattr(evaluator, 'load_stock_data'):
            fallback_df = evaluator.load_stock_data(clean_sym)
            if fallback_df is not None and not fallback_df.empty:
                fallback_df = fallback_df.copy()
                if 'symbol' not in fallback_df.columns:
                    fallback_df['symbol'] = clean_sym
                return fallback_df
    except Exception:
        pass

    return pd.DataFrame()


def get_no2_current_candidates(min_score: float = 65.0, target_date: str = None) -> list:
    """Lấy danh sách các cổ phiếu Nền Số 2 hiện tại từ Data Mart."""
    import json
    candidates_file = os.path.join(BASE_DIR, "data_mart", "current_no2_candidates.json")
    if not os.path.exists(candidates_file):
        return []
    try:
        with open(candidates_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if target_date:
            data = [x for x in data if x.get("date") == target_date]
        else:
            dates = [x.get("date", "") for x in data if x.get("date")]
            if dates:
                max_d = max(dates)
                data = [x for x in data if x.get("date") == max_d]
        # Filter min score and sort
        res = [x for x in data if x.get("no2_score", 0) >= min_score]
        res.sort(key=lambda x: (x.get("no2_score", 0), x.get("bms_score", 0)), reverse=True)
        return res
    except Exception:
        return []


def get_no2_detail_for_symbol(symbol: str, target_date: str = None) -> dict:
    """Bóc tách 6 Tầng định lượng No2 cho 1 cổ phiếu cụ thể."""
    clean_sym = symbol.strip().upper()
    df = load_stock_dat_df(clean_sym)
    if df is None or df.empty or len(df) < 80:
        return {"status": "error", "message": f"Không đủ dữ liệu lịch sử cho mã {clean_sym}"}
    
    target_idx = None
    if target_date:
        match_idx = df.index[df['time'] == target_date].tolist()
        if match_idx:
            target_idx = match_idx[0]
            
    res = detect_no2_in_df(df, target_idx=target_idx)
    res["symbol"] = clean_sym
    return res

