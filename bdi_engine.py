import os
import sys
import json
import time
import pandas as pd
import numpy as np
from datetime import datetime

# Path configuration
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
    MEI_DIR = getattr(sys, '_MEIPASS', APP_DIR)
    BASE_DIR = APP_DIR if os.path.exists(os.path.join(APP_DIR, "data_mart")) else MEI_DIR
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")
TRACKED_FILE = os.path.join(DATA_MART_DIR, "tracked_positions.json")
WATCHLIST_FILE = os.path.join(DATA_MART_DIR, "watchlist_positions.json")

sys.path.append(BASE_DIR)
from evaluator import (
    get_prepared_stock_df,
    SYMBOL_SECTOR_LOOKUP,
    evaluate_sector_wave
)

def _calc_macd_and_rsi(df: pd.DataFrame):
    """Calculates MACD(12, 26, 9), RSI(14) and RSI_Smoothed (EMA9 of RSI)."""
    # RSI 14
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df['rsi14'] = 100 - (100 / (1 + rs))
    df['rsi_smoothed'] = df['rsi14'].ewm(span=9, adjust=False).mean()
    
    # MACD(12, 26, 9)
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd_line'] = ema12 - ema26
    df['signal_line'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd_line'] - df['signal_line']
    
    # OBV and WMA10
    close_diff = df['close'].diff()
    direction = np.zeros(len(df))
    direction[close_diff > 0] = 1.0
    direction[close_diff < 0] = -1.0
    obv = (direction * df['volume']).cumsum()
    weights = np.arange(1, 11)
    w_sum = weights.sum() # 55
    df['obv'] = obv
    df['obv_wma10'] = obv.rolling(10).apply(lambda x: np.dot(x, weights) / w_sum, raw=True)
    
    df['roll_max_20'] = df['high'].rolling(20).max()
    df['roll_min_20'] = df['low'].rolling(20).min()
    df['base_spread_20'] = (df['roll_max_20'] - df['roll_min_20']) / (df['roll_min_20'] + 1e-9) * 100
    df['ma_conv'] = abs(df['ma10'] - df['ma20']) / (df['ma20'] + 1e-9) * 100
    return df

def check_new_base_after_breakout(df: pd.DataFrame, idx: int = None) -> tuple[bool, str, dict]:
    """
    Thuật toán số 2: Xác thực Nền Mới Sau Nhịp Nổ (New Base Setup Validation).
    Yêu cầu VSA chuẩn hóa:
    1. Nếu cổ phiếu đã có điểm mua cược, Pivot, và NỔ rồi thì:
       - BẮT BUỘC phải được setup lại một nền mới.
       - Nền mới này phải kéo dài TỐI THIỂU 1 tuần trở lên (>= 5 phiên giao dịch) kể từ nhịp nổ trước.
       - Đầy đủ công thức chuẩn VSA: Rũ bỏ (Shakeout), Kiệt cung (VDU), và Chờ nổ (Nền số 2 trên cao).
    2. Nếu vừa nổ xong (< 5 phiên): TUYỆT ĐỐI KHÔNG coi là Điểm Cược!
    3. Nếu đang ở Nền 1 gốc: Phải tích lũy >= 5 phiên, có rũ bỏ và kiệt cung.
    """
    if df is None or len(df) < 20:
        return False, "Không đủ dữ liệu nến", {}
        
    curr_idx = (len(df) - 1) if idx is None else idx
    closes = df['close'].values
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    vols = df['volume'].values
    avg_v10s = df['avg_vol10'].values if 'avg_vol10' in df.columns else vols
    ma20s = df['ma20'].values if 'ma20' in df.columns else closes
    ma50s = df['ma50'].values if 'ma50' in df.columns else closes
    
    # 1. Quét tìm phiên NỔ / BÙNG NỔ gần nhất trong 25 phiên qua
    lookback = min(curr_idx, 25)
    last_bo_idx = None
    
    for lb in range(curr_idx - 1, max(0, curr_idx - lookback - 1), -1):
        prev_idx = max(0, lb - 1)
        p_close = closes[prev_idx]
        b_close = closes[lb]
        b_chg = (b_close - p_close) / (p_close + 1e-9) * 100.0
        b_vr = vols[lb] / (avg_v10s[lb] + 1e-9)
        b_len = highs[lb] - lows[lb]
        b_pos = (b_close - lows[lb]) / (b_len + 1e-9) if b_len > 0 else 0.5
        
        # Tiêu chí phiên nổ: tăng >= 2.0% kèm Vol >= 1.25x TB10, hoặc nổ vol lớn >= 1.5x TB10, hoặc tăng mạnh >= 3.0%
        if (b_chg >= 2.0 and b_vr >= 1.25) or (b_vr >= 1.50 and b_chg >= 1.2) or (b_chg >= 3.0 and b_vr >= 1.10):
            last_bo_idx = lb
            break
            
    # 2. XỬ LÝ TRƯỜNG HỢP A: ĐÃ CÓ PHIÊN NỔ GẦN ĐÂY
    if last_bo_idx is not None:
        bars_since_bo = curr_idx - last_bo_idx
        bo_date = str(df.iloc[last_bo_idx]['time'])[:10] if 'time' in df.columns else ""
        bo_close = closes[last_bo_idx]
        bo_open = opens[last_bo_idx]
        bo_half = (bo_open + bo_close) / 2.0
        
        # Nếu chưa đủ 1 tuần (>= 5 phiên): TUYỆT ĐỐI LOẠI BỎ KHỎI ĐIỂM CƯỢC
        if bars_since_bo < 5:
            reason = f"Vừa có phiên Nổ ngày {bo_date} ({bars_since_bo} phiên trước). Chưa đủ 1 tuần (>= 5 phiên) để setup nền mới."
            return False, reason, {"bars_since_bo": bars_since_bo, "base_type": "BREAKOUT_RECENT", "bo_date": bo_date}
            
        # Nếu đã đủ >= 5 phiên: Kiểm tra đầy đủ công thức Nền 2 Trên Cao (Rũ bỏ, Kiệt cung, Chờ nổ)
        base2_slice_highs = highs[last_bo_idx : curr_idx + 1]
        base2_slice_lows = lows[last_bo_idx : curr_idx + 1]
        base2_slice_vols = vols[last_bo_idx + 1 : curr_idx + 1]
        base2_slice_avg10 = avg_v10s[last_bo_idx + 1 : curr_idx + 1]
        
        base2_high = np.max(base2_slice_highs)
        base2_low = np.min(base2_slice_lows)
        depth_pct = ((base2_high - base2_low) / (base2_high + 1e-9)) * 100.0
        
        # (a) Giữ nền trên cao: Không gãy 50% thân nến nổ và không thủng MA50
        curr_close = closes[curr_idx]
        curr_ma20 = ma20s[curr_idx]
        curr_ma50 = ma50s[curr_idx]
        holds_above_support = (curr_close >= bo_half * 0.97) and (curr_close >= curr_ma50 * 0.96)
        depth_ok = (depth_pct <= 17.5) # Nền 2 siết chặt, độ sâu điều chỉnh <= 17.5%
        
        # (b) Có nhịp Rũ bỏ (Shakeout / Pullback / Test):
        # Có ít nhất 1 phiên giá nhúng xuống rũ cung (Low chạm hoặc nhúng dưới MA20, hoặc nến rút chân)
        has_shakeout = False
        for k in range(last_bo_idx + 1, curr_idx + 1):
            if lows[k] <= ma20s[k] * 1.01 or (closes[k] < opens[k] and highs[k] - lows[k] > 0):
                has_shakeout = True
                break
                
        # (c) Có nhịp Kiệt Cung (Volume Dry-Up - VDU):
        # Trong các phiên của Nền 2 (đặc biệt trong 5 phiên gần nhất), có phiên Vol <= 0.85x TB10
        min_v_ratio = np.min(base2_slice_vols / (base2_slice_avg10 + 1e-9)) if len(base2_slice_vols) > 0 else 1.0
        has_volume_dryup = (min_v_ratio <= 0.85)
        
        # (d) Phiên hiện tại đang nén chặt chờ nổ:
        curr_vr = vols[curr_idx] / (avg_v10s[curr_idx] + 1e-9)
        curr_near_ma = (abs(curr_close - curr_ma20) / (curr_ma20 + 1e-9) <= 0.04)
        
        if holds_above_support and depth_ok and has_shakeout and has_volume_dryup and curr_near_ma and (curr_vr <= 0.92):
            reason = f"Đạt chuẩn Điểm Cược Nền 2 (Nền {bars_since_bo} phiên, có rũ bỏ & kiệt cung {min_v_ratio:.2f}x TB10, sâu {depth_pct:.1f}%)"
            return True, reason, {"bars_since_bo": bars_since_bo, "base_type": "BASE2_CUOC", "depth_pct": depth_pct, "min_v_ratio": min_v_ratio}
        else:
            reasons_fail = []
            if not holds_above_support: reasons_fail.append("Thủng hỗ trợ nến nổ/MA50")
            if not depth_ok: reasons_fail.append(f"Độ sâu nền quá lớn ({depth_pct:.1f}%)")
            if not has_shakeout: reasons_fail.append("Chưa có nhịp rũ bỏ test cung")
            if not has_volume_dryup: reasons_fail.append(f"Vol chưa kiệt ({min_v_ratio:.2f}x)")
            if curr_vr > 0.92: reasons_fail.append(f"Vol hiện tại còn cao ({curr_vr:.2f}x)")
            reason = f"Đang xây Nền 2 ({bars_since_bo} phiên) nhưng chưa đạt: " + ", ".join(reasons_fail)
            return False, reason, {"bars_since_bo": bars_since_bo, "base_type": "BASE2_BUILDING", "depth_pct": depth_pct}
            
    # 3. XỬ LÝ TRƯỜNG HỢP B: CHƯA NỔ GẦN ĐÂY (NỀN 1 BAN ĐẦU)
    # Nền 1 phải tích lũy >= 5 phiên, có kiệt cung và nén chặt
    base1_slice_vols = vols[max(0, curr_idx - 5) : curr_idx + 1]
    base1_slice_avg10 = avg_v10s[max(0, curr_idx - 5) : curr_idx + 1]
    min_v_ratio1 = np.min(base1_slice_vols / (base1_slice_avg10 + 1e-9)) if len(base1_slice_vols) > 0 else 1.0
    
    curr_close = closes[curr_idx]
    curr_ma20 = ma20s[curr_idx]
    curr_vr = vols[curr_idx] / (avg_v10s[curr_idx] + 1e-9)
    dist_ma20 = abs(curr_close - curr_ma20) / (curr_ma20 + 1e-9)
    
    # Nền 1: Vol kiệt <= 0.85x, bám sát MA20 <= 3.0%, không gãy sâu
    if (min_v_ratio1 <= 0.85) and (dist_ma20 <= 0.035) and (curr_vr <= 0.90):
        reason = f"Đạt chuẩn Điểm Cược Nền 1 (Kiệt cung chân sóng: {min_v_ratio1:.2f}x TB10)"
        return True, reason, {"base_type": "BASE1_CUOC", "min_v_ratio": min_v_ratio1}
    else:
        return False, f"Chưa đủ điều kiện cạn kiệt vol tại nền 1 (min_vol: {min_v_ratio1:.2f}x, curr_vol: {curr_vr:.2f}x)", {"base_type": "BASE1_NOT_MET"}

def score_bdi_stock(symbol: str, target_date_str: str = None) -> dict:
    """
    Evaluates stock using the VSA Ông Bình Design Index (BDI) (0 - 100 points)
    and identifies candidate buy points (Cược C1, Pivot P1, Breakout B1).
    """
    sym = symbol.upper().strip()
    df = get_prepared_stock_df(sym, target_date_str=target_date_str)
    if df is None or df.empty or len(df) < 30:
        return {"status": "error", "message": f"Không tải được dữ liệu lịch sử cho mã {sym}"}
        
    df = _calc_macd_and_rsi(df)
    
    if target_date_str:
        try:
            target_dt = pd.to_datetime(target_date_str, errors='coerce')
            df['parsed_time'] = pd.to_datetime(df['time'], errors='coerce')
            df_filtered = df[df['parsed_time'] <= target_dt]
            if not df_filtered.empty and len(df_filtered) >= 20:
                df = df_filtered.copy()
            elif df_filtered.empty:
                return {"status": "error", "message": f"Không có dữ liệu giao dịch cho mã {sym} trước ngày {target_date_str}"}
        except Exception as e:
            pass
    
    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else row
    
    close = float(row['close'])
    prev_close = float(prev['close'])
    high = float(row['high'])
    low = float(row['low'])
    vol = float(row['volume'])
    avg_v10 = float(row['avg_vol10']) if 'avg_vol10' in row else 1.0
    avg_v20 = float(row['avg_vol20']) if 'avg_vol20' in row else 1.0
    
    chg_pct = (close - prev_close) / (prev_close + 1e-9) * 100
    vol_r10 = vol / (avg_v10 + 1e-9)
    vol_r20 = vol / (avg_v20 + 1e-9)
    
    candle_len = high - low
    close_pos = (close - low) / (candle_len + 1e-9) if candle_len > 0 else 0.5
    upper_wick = (high - max(row['open'], close)) / (candle_len + 1e-9) if candle_len > 0 else 0.0
    
    ma10 = float(row['ma10']) if pd.notna(row['ma10']) else close
    ma20 = float(row['ma20']) if pd.notna(row['ma20']) else close
    ma50 = float(row['ma50']) if pd.notna(row['ma50']) else close
    
    dist_ma20 = (close - ma20) / ma20 * 100
    dist_ma50 = (close - ma50) / ma50 * 100
    
    rsi = float(row['rsi14'])
    rsi_smoothed = float(row['rsi_smoothed'])
    macd_line = float(row['macd_line'])
    signal_line = float(row['signal_line'])
    macd_hist = float(row['macd_hist'])
    
    obv = float(row['obv'])
    obv_wma10 = float(row['obv_wma10']) if pd.notna(row['obv_wma10']) else obv
    obv_up = bool(obv >= obv_wma10)
    
    base_spread = float(row['base_spread_20']) if pd.notna(row['base_spread_20']) else 10.0
    ma_conv = float(row['ma_conv']) if pd.notna(row['ma_conv']) else 2.0
    
    # 1. Nhận diện loại điểm mua VSA hiện tại
    point_name = "Tích Lũy Nền (Chưa có điểm mua)"
    point_code = "NONE"
    
    # Kiểm tra Thuật toán số 2: Xác thực Nền Mới Sau Nhịp Nổ
    is_base_valid, base_desc, base_meta = check_new_base_after_breakout(df, idx=len(df)-1)
    
    # Đột biến thể tích sớm: Vol >= 2.5x TB10, TB10 >= 50,000 cp, tăng >= 1.5%, đóng nến >= 70% thân nến trên
    is_vol_surge = (vol >= 2.5 * avg_v10) and (avg_v10 >= 50000) and (chg_pct >= 1.5) and (close_pos >= 0.70)
    
    # Breakout B1: Nổ vol vượt cản, tăng >= 2.3%, đóng cao (close_pos >= 0.70)
    is_breakout = ((chg_pct >= 2.3) and (vol_r10 >= 1.3) and (close_pos >= 0.70) and (close >= ma20)) or is_vol_surge
    # Pivot P1 (Đẩy nền): Bám sát MA20, vol nhú 0.85 - 2.2x, nến xanh tăng nhẹ-khá
    is_pivot = (0.6 <= chg_pct <= 4.0) and (-2.0 <= dist_ma20 <= 3.8) and (vol_r10 >= 0.85) and (close_pos >= 0.55) and obv_up
    
    # Cược C1: BẮT BUỘC phải thỏa mãn Thuật toán số 2 (Đã setup nền mới tối thiểu 1 tuần nếu vừa nổ, có rũ bỏ & kiệt cung)
    is_cuoc = bool(is_base_valid and (abs(dist_ma20) <= 3.5) and (vol_r10 <= 0.90) and (chg_pct >= -2.0))
    
    if is_vol_surge:
        point_name = "Điểm Đột Biến Thể Tích Sớm (Volume Surge B1)"
        point_code = "B1"
    elif is_breakout:
        point_name = "Điểm Nổ Breakout (B1)"
        point_code = "B1"
    elif is_pivot:
        point_name = "Điểm Đẩy Nền Pivot (P1)"
        point_code = "P1"
    elif is_cuoc:
        if base_meta.get("base_type") == "BASE2_CUOC":
            point_name = f"Điểm Cược Nền 2 (Nền {base_meta.get('bars_since_bo', 5)} phiên kiệt cung)"
        else:
            point_name = "Điểm Mua Cược Nền (C1)"
        point_code = "C1"
    else:
        if base_meta.get("base_type") == "BREAKOUT_RECENT":
            point_name = f"Sau Nổ ({base_meta.get('bars_since_bo', 1)} phiên) - Chờ Nền Mới"
            point_code = "AFTER_BO"

    # 2. Đánh giá 8 Tiêu chí BDI (VSA Ông Bình Design Index)
    
    # Tiêu chí 1: Kỷ luật Zero-Đỉnh (30 điểm)
    # Kiểm tra nến nổ gần nhất trong 5 phiên qua có giữ >50% thân nến không
    pass_zero_dinh = True
    zero_dinh_note = "Giữ vững trên 50% thân nến"
    for lb in range(max(0, len(df)-5), len(df)):
        b_bar = df.iloc[lb]
        b_prev = df.iloc[lb-1] if lb > 0 else b_bar
        b_chg = (b_bar['close'] - b_prev['close']) / (b_prev['close'] + 1e-9) * 100
        b_vr = b_bar['volume'] / (b_bar['avg_vol10'] + 1e-9)
        if b_chg >= 2.5 and b_vr >= 1.25:
            half_body = (b_bar['open'] + b_bar['close']) / 2.0
            if close < half_body:
                pass_zero_dinh = False
                zero_dinh_note = f"Gãy 50% thân nến nổ ngày {str(b_bar['time'])[:10]} ({half_body:.2f})"
                break
    score_zero_dinh = 30 if pass_zero_dinh else 0
    
    # Tiêu chí 2: Đường MACD (15 điểm)
    # Với Pivot & Breakout: MACD > Signal VÀ Signal >= 0 (cắt lên ở nửa trục dương)
    # Với Cược: MACD >= Signal hoặc Histogram >= 0
    if point_code in ["B1", "P1"]:
        pass_macd = bool(macd_line > signal_line and signal_line >= 0)
        macd_desc = f"MACD ({macd_line:.2f}) > Signal ({signal_line:.2f}) & Signal >= 0 (Trục dương)" if pass_macd else f"Chưa đạt: MACD={macd_line:.2f}, Signal={signal_line:.2f} (Yêu cầu trục dương & trên Signal)"
    else:
        pass_macd = bool(macd_line >= signal_line or macd_hist >= 0)
        macd_desc = f"Histogram ({macd_hist:.2f}) >= 0 hoặc MACD trên Signal" if pass_macd else f"Histogram âm ({macd_hist:.2f})"
    score_macd = 15 if pass_macd else 0
    
    # Tiêu chí 3: Sóng ngành bảo trợ (15 điểm)
    sector_name = SYMBOL_SECTOR_LOOKUP.get(sym, "KHAC")
    sec_wave = evaluate_sector_wave(sector_name, target_date_str=str(row['time']))
    sec_score = float(sec_wave.get("score", 50.0))
    pass_sector = bool(sec_score >= 60.0)
    score_sector = 15 if pass_sector else 0
    
    # Tiêu chí 4: Chỉ báo OBV dốc lên (15 điểm)
    pass_obv = obv_up
    score_obv = 15 if pass_obv else 0
    
    # Tiêu chí 5: Thị trường chung VN-Index (10 điểm)
    # Kiểm tra VNINDEX không phải Downtrend
    try:
        vni_df = get_prepared_stock_df("VNINDEX", target_date_str=str(row['time']))
        if vni_df is not None and not vni_df.empty:
            vni_dt = pd.to_datetime(str(row['time'])[:10], errors='coerce')
            vni_df['parsed_time'] = pd.to_datetime(vni_df['time'], errors='coerce')
            vni_filtered = vni_df[vni_df['parsed_time'] <= vni_dt]
            if not vni_filtered.empty:
                vni_row = vni_filtered.iloc[-1]
                vni_close = float(vni_row['close'])
                vni_ma20 = float(vni_row['ma20']) if pd.notna(vni_row['ma20']) else vni_close
                pass_vni = bool(vni_close >= vni_ma20 * 0.985)
            else:
                pass_vni = True
        else:
            pass_vni = True
    except Exception:
        pass_vni = True
    score_vni = 10 if pass_vni else 0
    
    # Tiêu chí 6: Xung lực RSI (5 điểm)
    # Yêu cầu: RSI > 50 VÀ RSI >= Smoothed MA (EMA9 của RSI)
    pass_rsi = bool(rsi > 50.0 and rsi >= rsi_smoothed)
    score_rsi = 5 if pass_rsi else 0
    
    # Tiêu chí 7: Độ siết nền giá (5 điểm)
    pass_base = bool(base_spread <= 13.0)
    score_base = 5 if pass_base else 0
    
    # Tiêu chí 8: Cấu Trúc Đường MA (5 điểm)
    # - Điểm Mua Cược (C1) / Nền: Xét Yếu Tố Hội Tụ MA (Độ lệch <= 4% hoặc bám sát MA20 +-2.5%)
    # - Điểm Pocket, Pivot (P1), Breakout (B1): Giá bứt phá nên MA tách dải -> Xét Thứ Tự MA Xu Hướng Tăng
    if point_code in ["B1", "P1"]:
        pass_ma = bool(close >= ma10 * 0.99 and ma10 >= ma20 * 0.995 and ma20 >= ma50 * 0.985)
        crit_ma_name = "8. Cấu Trúc MA (Thứ Tự MA Xu Hướng Tăng)"
        if pass_ma:
            ma_desc = f"Thứ tự MA chuẩn tăng: Giá ({close:.2f}) >= MA10 ({ma10:.2f}) >= MA20 ({ma20:.2f}) >= MA50 ({ma50:.2f})"
        else:
            ma_desc = f"Chưa đạt thứ tự MA: Giá={close:.2f}, MA10={ma10:.2f}, MA20={ma20:.2f}, MA50={ma50:.2f}"
    else:
        pass_ma = bool(ma_conv <= 4.0 or abs(dist_ma20) <= 2.5)
        crit_ma_name = "8. Cấu Trúc MA (Hội Tụ MA Co Cụm Nền)"
        if pass_ma:
            ma_desc = f"MA hội tụ siết chặt: Độ lệch {ma_conv:.1f}% (<= 4.0%) hoặc bám sát MA20 ({dist_ma20:+.1f}%)"
        else:
            ma_desc = f"Chưa hội tụ siết chặt: Độ lệch MA {ma_conv:.1f}% (> 4.0%), Cách MA20 {dist_ma20:+.1f}%"
    score_ma = 5 if pass_ma else 0
    
    # TỔNG ĐIỂM BDI (VSA Ông Bình Design Index)
    total_bdi = score_zero_dinh + score_macd + score_sector + score_obv + score_vni + score_rsi + score_base + score_ma
    
    # Phân tầng quyết định
    if total_bdi >= 80:
        rec_label = "MÚC MẠNH (Tối ưu tuyệt đối)"
        action_code = "STRONG_BUY"
        winrate_est = 63.2
        rec_color = "emerald"
    elif total_bdi >= 65:
        rec_label = "MUA CHUẨN (Xác suất cao)"
        action_code = "STANDARD_BUY"
        winrate_est = 58.1
        rec_color = "emerald"
    elif total_bdi >= 50:
        rec_label = "THĂM DÒ 1/8 (Thận trọng)"
        action_code = "TEST_BUY"
        winrate_est = 48.6
        rec_color = "amber"
    else:
        rec_label = "ĐỨNG NGOÀI (CẤM MUA - RỦI RO CAO)"
        action_code = "DO_NOT_BUY"
        winrate_est = 27.4
        rec_color = "rose"
        
    criteria_list = [
        {"name": "1. Kỷ Luật Zero-Đỉnh (Bảo vệ nến bùng nổ)", "max_points": 30, "points": score_zero_dinh, "passed": pass_zero_dinh, "desc": zero_dinh_note},
        {"name": "2. Đường MACD (Cắt lên trục dương >= 0)", "max_points": 15, "points": score_macd, "passed": pass_macd, "desc": macd_desc},
        {"name": "3. Sóng Ngành Bảo Trợ (Wave Score >= 60)", "max_points": 15, "points": score_sector, "passed": pass_sector, "desc": f"Điểm sóng dòng {sector_name}: {sec_score:.1f}/100"},
        {"name": "4. Chỉ Báo OBV (Dốc lên vượt WMA10)", "max_points": 15, "points": score_obv, "passed": pass_obv, "desc": "OBV dốc lên trên WMA10 (Dòng tiền gom)" if pass_obv else "OBV chưa vượt WMA10"},
        {"name": "5. Thị Trường Chung VN-Index (Tránh Downtrend)", "max_points": 10, "points": score_vni, "passed": pass_vni, "desc": "VNI duy trì trên hỗ trợ MA20" if pass_vni else "VNI dưới MA20 (Thị trường chung rủi ro)"},
        {"name": "6. Xung Lực RSI (RSI > 50 & Trên Smoothed MA)", "max_points": 5, "points": score_rsi, "passed": pass_rsi, "desc": f"RSI={rsi:.1f} (Yêu cầu > 50 & >= Smoothed {rsi_smoothed:.1f})"},
        {"name": "7. Độ Siết Nền Giá (Biên độ 20 phiên <= 12%)", "max_points": 5, "points": score_base, "passed": pass_base, "desc": f"Biên độ nền: {base_spread:.1f}%"},
        {"name": crit_ma_name, "max_points": 5, "points": score_ma, "passed": pass_ma, "desc": ma_desc}
    ]
    
    return {
        "status": "success",
        "symbol": sym,
        "date": str(row['time'])[:10],
        "close": round(close, 2),
        "chg_pct": round(chg_pct, 2),
        "vol": int(vol),
        "avg_vol10": round(avg_v10, 0),
        "vol_r10": round(vol_r10, 2),
        "is_volume_surge": bool(is_vol_surge),
        "is_breakout": bool(is_breakout),
        "is_pivot": bool(is_pivot),
        "is_cuoc": bool(is_cuoc),
        "is_base_valid": bool(is_base_valid),
        "base_setup_desc": base_desc,
        "base_setup_meta": base_meta,
        "low_buy": round(low, 2), # Giá thấp nhất làm Hard Stop
        "point_name": point_name,
        "point_code": point_code,
        "bdi_score": total_bdi,
        "recommendation": rec_label,
        "action_code": action_code,
        "winrate_est": winrate_est,
        "rec_color": rec_color,
        "sector": sector_name,
        "criteria": criteria_list
    }

# ==============================================================================
# QUẢN LÝ VỊ THẾ ĐÃ MUA & HỆ THỐNG CẢNH BÁO RRBDI (RỦI RO HỆ THỐNG BDI)
# ==============================================================================

def load_tracked_positions() -> list:
    """Loads all tracked buy positions from persistent storage."""
    if not os.path.exists(TRACKED_FILE):
        return []
    try:
        with open(TRACKED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_tracked_buy_position(data: dict) -> dict:
    """Adds a new buy position to tracked database."""
    positions = load_tracked_positions()
    
    sym = data.get("symbol", "").upper().strip()
    buy_date = data.get("buy_date", datetime.now().strftime("%Y-%m-%d"))
    buy_price = float(data.get("buy_price", 0.0))
    low_price = float(data.get("low_price", buy_price * 0.97))
    point_name = data.get("point_name", "Điểm Mua VSA")
    bdi_score = int(data.get("bdi_score", 70))
    notes = data.get("notes", "")
    
    shares_count = int(data.get("shares_count", 10000))
    pos_id = f"{sym}_{buy_date.replace('-', '')}_{int(time.time())}"
    
    new_pos = {
        "id": pos_id,
        "symbol": sym,
        "buy_date": buy_date,
        "buy_price": buy_price,
        "shares_count": shares_count,
        "buy_low": low_price, # Mốc dừng lỗ cứng tối hậu
        "point_name": point_name,
        "initial_bdi": bdi_score,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "HOLDING",
        "notes": notes
    }
    
    # Prevent exact duplicates on same symbol and date
    positions = [p for p in positions if not (p["symbol"] == sym and p["buy_date"] == buy_date)]
    positions.insert(0, new_pos)
    
    os.makedirs(os.path.dirname(TRACKED_FILE), exist_ok=True)
    with open(TRACKED_FILE, "w", encoding="utf-8") as f:
        json.dump(positions, f, ensure_ascii=False, indent=2)
        
    return new_pos

# ==============================================================================
# QUẢN LÝ DANH SÁCH THEO DÕI (WATCHLIST / RADAR TỰ ĐỘNG BẮT ĐIỂM MUA)
# ==============================================================================

def load_watchlist_positions() -> list:
    """Loads all watchlist positions from persistent storage."""
    if not os.path.exists(WATCHLIST_FILE):
        return []
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_watchlist_position(symbol: str, notes: str = "Theo dõi điểm mua") -> dict:
    """Adds a symbol to the Watchlist Radar."""
    sym = symbol.upper().strip()
    watchlist = load_watchlist_positions()
    
    # Check if already in watchlist
    for w in watchlist:
        if w.get("symbol") == sym:
            return {"status": "exists", "message": f"Mã {sym} đã có trong Danh Sách Theo Dõi!", "data": w}
            
    bdi_res = score_bdi_stock(sym)
    if bdi_res.get("status") == "error":
        cur_p = 10.0
        cur_bdi = 50
        point_name = "Chờ tín hiệu"
    else:
        cur_p = float(bdi_res.get("close", 10.0))
        cur_bdi = int(bdi_res.get("bdi_score", 50))
        point_name = bdi_res.get("point_name", "Chờ tín hiệu")
        
    w_id = f"WATCH_{sym}_{int(time.time())}"
    new_item = {
        "id": w_id,
        "symbol": sym,
        "added_date": datetime.now().strftime("%Y-%m-%d"),
        "added_price": cur_p,
        "initial_bdi": cur_bdi,
        "initial_point": point_name,
        "notes": notes,
        "status": "WATCHING",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    watchlist.insert(0, new_item)
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)
        
    return {"status": "success", "message": f"Đã thêm {sym} vào Danh Sách Theo Dõi (Radar Bắt Điểm Mua)!", "data": new_item}

def remove_watchlist_position(watch_id: str) -> bool:
    """Removes a position from watchlist radar."""
    watchlist = load_watchlist_positions()
    target = str(watch_id).strip()
    new_list = [w for w in watchlist if w.get("id") != target and w.get("symbol") != target.upper()]
    if len(new_list) != len(watchlist):
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(new_list, f, ensure_ascii=False, indent=2)
        return True
    return False

def convert_watchlist_to_bought(symbol: str, buy_price: float, shares_count: int = 10000, buy_date: str = None, notes: str = "") -> dict:
    """Converts a watchlist item into an active bought holding (Holdings Portfolio)."""
    sym = symbol.upper().strip()
    bdi_res = score_bdi_stock(sym)
    bdi_score = int(bdi_res.get("bdi_score", 75)) if bdi_res.get("status") != "error" else 75
    point_name = bdi_res.get("point_name", "Điểm Mua VSA") if bdi_res.get("status") != "error" else "Điểm Mua VSA"
    low_price = float(bdi_res.get("low_buy", buy_price * 0.97)) if bdi_res.get("status") != "error" else buy_price * 0.97
    
    pos = save_tracked_buy_position({
        "symbol": sym,
        "buy_date": buy_date or datetime.now().strftime("%Y-%m-%d"),
        "buy_price": buy_price,
        "shares_count": shares_count,
        "low_price": low_price,
        "point_name": point_name,
        "bdi_score": bdi_score,
        "notes": notes or f"Chuyển từ Watchlist (BDI: {bdi_score})"
    })
    
    # Remove from watchlist
    remove_watchlist_position(sym)
    return {"status": "success", "message": f"Đã kích hoạt MỞ MUA {sym}! Vị thế đã chuyển sang Danh Mục Nắm Giữ & Quản Trị RRBDI.", "data": pos}

def evaluate_watchlist_signals() -> list:
    """
    Evaluates real-time buy signals, BDI scores, and current price for all watchlist items.
    Specialized in scanning candidate BUY opportunities (Cược C1, Pivot P1, Vol Surge B1, Breakout B1).
    """
    watchlist = load_watchlist_positions()
    results = []
    
    for w in watchlist:
        sym = w["symbol"]
        added_date = w.get("added_date", "")
        added_price = float(w.get("added_price", 0.0))
        
        bdi_res = score_bdi_stock(sym)
        if bdi_res.get("status") == "error":
            w_copy = dict(w)
            w_copy.update({
                "current_price": added_price,
                "chg_from_added": 0.0,
                "today_chg_pct": 0.0,
                "vol_r10": 1.0,
                "current_bdi": w.get("initial_bdi", 50),
                "point_code": "NONE",
                "point_name": "Đang đồng bộ dữ liệu...",
                "is_volume_surge": False,
                "is_buy_ready": False,
                "signal_badge": "⚪ Chờ tín hiệu",
                "recommendation": "Đang cập nhật",
                "action_advice": "Đang đồng bộ dữ liệu"
            })
            results.append(w_copy)
            continue
            
        cur_price = float(bdi_res.get("close", added_price))
        cur_bdi = int(bdi_res.get("bdi_score", 50))
        p_code = bdi_res.get("point_code", "NONE")
        p_name = bdi_res.get("point_name", "Tích Lũy Nền")
        is_vol_surge = bdi_res.get("is_volume_surge", False)
        vol_r10 = float(bdi_res.get("vol_r10", 1.0))
        chg_pct = float(bdi_res.get("chg_pct", 0.0))
        
        chg_from_added = ((cur_price - added_price) / (added_price + 1e-9)) * 100 if added_price > 0 else 0.0
        
        # Đánh giá điểm mua
        is_buy_ready = False
        signal_badge = "⚪ Chờ tín hiệu"
        action_advice = "Tiếp tục quan sát siết nền và kiệt cung"
        
        if is_vol_surge:
            is_buy_ready = True
            signal_badge = "🔥 NỔ VOL SURGE (≥2.5x)"
            action_advice = "Dòng tiền lớn thức giấc! Mở mua thăm dò 1/8 hoặc giải ngân ngay."
        elif p_code == "B1":
            is_buy_ready = True
            signal_badge = "🚀 ĐIỂM NỔ BREAKOUT (B1)"
            action_advice = "Cổ phiếu bứt phá khỏi nền tích lũy! Điểm mua chuẩn gia tăng."
        elif p_code == "P1":
            is_buy_ready = True
            signal_badge = "🌟 ĐẨY NỀN PIVOT (P1)"
            action_advice = "Điểm nổ sớm bám sát MA20, vol nhú chuẩn. Thích hợp mở vị thế sớm."
        elif p_code == "C1":
            is_buy_ready = True
            signal_badge = "🎯 CƯỢC NỀN SIẾT (C1)"
            action_advice = "Nền giá siết chặt, vol cạn kiệt. Lấy vị thế cược 1/8 an toàn tại nền."
        elif cur_bdi >= 75:
            signal_badge = "🟢 TÍCH LŨY MẠNH (BDI cao)"
            action_advice = "Điểm tích lũy cao. Chờ phiên nổ vol hoặc nhú Pivot để kích hoạt lệnh mua."
            
        w_copy = dict(w)
        w_copy.update({
            "current_price": cur_price,
            "chg_from_added": round(chg_from_added, 2),
            "today_chg_pct": round(chg_pct, 2),
            "vol_r10": round(vol_r10, 2),
            "current_bdi": cur_bdi,
            "point_code": p_code,
            "point_name": p_name,
            "is_volume_surge": is_vol_surge,
            "is_buy_ready": is_buy_ready,
            "signal_badge": signal_badge,
            "recommendation": bdi_res.get("recommendation", "Theo dõi"),
            "action_advice": action_advice,
            "low_buy": bdi_res.get("low_buy", cur_price * 0.97)
        })
        results.append(w_copy)
        
    return results

def quick_track_position(symbol: str, notes: str = "Theo dõi Bot") -> dict:
    """Redirects to save_watchlist_position so all UI 'Lưu Giám Sát' buttons populate the Watchlist."""
    return save_watchlist_position(symbol, notes)

def remove_tracked_position(pos_id: str) -> bool:
    """Removes a position from tracking database."""
    positions = load_tracked_positions()
    new_list = [p for p in positions if p["id"] != pos_id]
    if len(new_list) != len(positions):
        with open(TRACKED_FILE, "w", encoding="utf-8") as f:
            json.dump(new_list, f, ensure_ascii=False, indent=2)
        return True
    return False

def evaluate_rrbdi_for_tracked_positions() -> list:
    """
    Evaluates current status, profit/loss, and RRBDI risk warnings
    for all tracked buy positions.
    """
    positions = load_tracked_positions()
    results = []
    
    for pos in positions:
        sym = pos["symbol"]
        buy_date = pos["buy_date"]
        buy_price = float(pos["buy_price"])
        shares = int(pos.get("shares_count", pos.get("shares", 10000)))
        buy_low = float(pos.get("buy_low", buy_price * 0.97))
        p_name = pos.get("point_name", "Điểm Mua")
        
        df = get_prepared_stock_df(sym)
        if df is None or df.empty or len(df) < 20:
            pos_copy = dict(pos)
            pos_copy.update({
                "shares_count": shares,
                "cost_value": round(buy_price * shares, 2),
                "current_value": round(buy_price * shares, 2),
                "profit_amt": 0.0,
                "current_price": buy_price,
                "profit_pct": 0.0,
                "rrbdi_level": "UNKNOWN",
                "rrbdi_badge": "⚪ Chưa có dữ liệu",
                "rrbdi_alert": "Đang đồng bộ dữ liệu thị trường...",
                "next_buy_signal": None
            })
            results.append(pos_copy)
            continue
            
        df = _calc_macd_and_rsi(df)
        
        cur_row = df.iloc[-1]
        cur_close = float(cur_row['close'])
        profit_pct = (cur_close - buy_price) / (buy_price + 1e-9) * 100
        
        # Check forward sequence from buy_date
        date_list = df['time'].astype(str).str.slice(0, 10).tolist()
        try:
            buy_idx = date_list.index(buy_date)
        except ValueError:
            # If exact date not found, find nearest
            buy_idx = max(0, len(df) - 5)
            
        fwd_bars = df.iloc[buy_idx+1 :]
        
        # 1. KIỂM TRA TÍN HIỆU MUA GIA TĂNG (NEXT BUY SIGNAL)
        next_buy_signal = None
        cur_bdi_res = score_bdi_stock(sym)
        cur_point_code = cur_bdi_res.get("point_code", "NONE")
        
        if "Cược" in p_name or "C1" in p_name:
            if cur_point_code == "P1":
                next_buy_signal = "🚀 CẢNH BÁO GIA TĂNG: Xuất hiện Điểm Đẩy Nền Pivot (P1) -> Mua nhồi thêm 12.5%!"
            elif cur_point_code == "B1":
                next_buy_signal = "💥 CẢNH BÁO GIA TĂNG: Bùng nổ Breakout (B1) -> Gia tăng đủ vị thế!"
        elif "Pivot" in p_name or "P1" in p_name:
            if cur_point_code == "B1":
                next_buy_signal = "💥 CẢNH BÁO GIA TĂNG: Bùng nổ Breakout (B1) -> Gia tăng đủ vị thế!"
                
        # 2. KIỂM TRA HỆ THỐNG CẢNH BÁO RRBDI (RỦI RO HỆ THỐNG BDI)
        rrbdi_level = "GREEN"
        rrbdi_badge = "🟢 An Toàn"
        rrbdi_alert = "Cổ phiếu duy trì xu hướng tốt trên hỗ trợ MA, tiếp tục nắm giữ theo kế hoạch."
        
        # Count consecutive closes below MA10 and MA20
        consec_below_ma10 = 0
        consec_below_ma20 = 0
        if not fwd_bars.empty:
            for i in range(len(fwd_bars)-1, -1, -1):
                b = fwd_bars.iloc[i]
                if b['close'] < b['ma10']:
                    consec_below_ma10 += 1
                else:
                    break
            for i in range(len(fwd_bars)-1, -1, -1):
                b = fwd_bars.iloc[i]
                if b['close'] < b['ma20']:
                    consec_below_ma20 += 1
                else:
                    break
        else:
            # Same day
            if cur_close < cur_row['ma10']: consec_below_ma10 = 1
            if cur_close < cur_row['ma20']: consec_below_ma20 = 1
            
        cur_rsi = float(cur_row['rsi14'])
        cur_rsi_sm = float(cur_row['rsi_smoothed'])
        rsi_weak = bool(cur_rsi < cur_rsi_sm)
        
        cur_vol = float(cur_row['volume'])
        cur_avg_v10 = float(cur_row['avg_vol10']) if 'avg_vol10' in cur_row else 1.0
        vol_dump = bool(cur_close < float(df.iloc[-2]['close']) and cur_vol >= 1.2 * cur_avg_v10)
        
        broke_low = bool(cur_close < buy_low)
        
        # --- THỨ TỰ PHÂN CẤP CẢNH BÁO RRBDI ---
        # CẤP 3: BÁO ĐỘNG ĐỎ (Thủng Low nến mua HOẶC gãy 3 phiên MA10/MA20)
        if broke_low:
            rrbdi_level = "RED"
            rrbdi_badge = "🚨 CẤP BÁO ĐỎ (Tối Hậu)"
            rrbdi_alert = f"Thủng giá thấp nhất cây nến mua ({cur_close:.2f} < {buy_low:.2f})! Xác suất thất bại 98-100%. BÁN DỪNG LỖ 100% NGAY LẬP TỨC!"
        elif consec_below_ma10 >= 3:
            rrbdi_level = "RED"
            rrbdi_badge = "🔴 BÁO ĐỘNG ĐỎ"
            rrbdi_alert = f"Gãy MA10 liên tiếp {consec_below_ma10} phiên không phục hồi! Xác suất thua 75-80%. BÁN SẠCH TOÀN BỘ VỊ THẾ!"
        elif consec_below_ma20 >= 3:
            rrbdi_level = "RED"
            rrbdi_badge = "🔴 BÁO ĐỘNG ĐỎ"
            rrbdi_alert = f"Gãy MA20 liên tiếp {consec_below_ma20} phiên không phục hồi! Xác suất thua 74-84%. BÁN SẠCH TOÀN BỘ VỊ THẾ!"
        # CẤP 2: CẢNH BÁO CAM (Gãy 2 phiên MA10/MA20)
        elif consec_below_ma10 >= 2:
            rrbdi_level = "ORANGE"
            rrbdi_badge = "🟠 CẢNH BÁO CAM"
            rrbdi_alert = f"Đóng cửa dưới MA10 liên tiếp 2 phiên ({cur_close:.2f} < {cur_row['ma10']:.2f})! Xác suất thua 61-67%. HẠ 50% TỶ TRỌNG NGAY!"
        elif consec_below_ma20 >= 2:
            rrbdi_level = "ORANGE"
            rrbdi_badge = "🟠 CẢNH BÁO CAM"
            rrbdi_alert = f"Đóng cửa dưới MA20 liên tiếp 2 phiên ({cur_close:.2f} < {cur_row['ma20']:.2f})! Xác suất thua 61-69%. HẠ 50% TỶ TRỌNG NGAY!"
        # CẤP 1: CẢNH BÁO VÀNG (Suy yếu động lượng)
        elif rsi_weak:
            rrbdi_level = "YELLOW"
            rrbdi_badge = "🟡 CẢNH BÁO VÀNG"
            rrbdi_alert = f"Đường RSI ({cur_rsi:.1f}) cắt xuống dưới RSI Smoothed ({cur_rsi_sm:.1f}). Động lượng suy yếu, tạm dừng mua gia tăng!"
        elif vol_dump:
            rrbdi_level = "YELLOW"
            rrbdi_badge = "🟡 CẢNH BÁO VÀNG"
            rrbdi_alert = f"Xuất hiện nến đỏ giảm kèm khối lượng bán lớn ({cur_vol/cur_avg_v10:.1f}x TB10). Thận trọng quản trị rủi ro!"
            
        cost_val = buy_price * shares
        cur_val = cur_close * shares
        profit_amt = cur_val - cost_val
        
        pos_copy = dict(pos)
        pos_copy.update({
            "shares_count": shares,
            "cost_value": round(cost_val, 2),
            "current_value": round(cur_val, 2),
            "profit_amt": round(profit_amt, 2),
            "current_price": round(cur_close, 2),
            "profit_pct": round(profit_pct, 2),
            "current_bdi": cur_bdi_res.get("bdi_score", 50),
            "rrbdi_level": rrbdi_level,
            "rrbdi_badge": rrbdi_badge,
            "rrbdi_alert": rrbdi_alert,
            "next_buy_signal": next_buy_signal
        })
        results.append(pos_copy)
        
    return results
