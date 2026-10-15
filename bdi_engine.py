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

def check_sbar_breakout(df: pd.DataFrame, idx: int = None) -> tuple[bool, str, dict]:
    """
    Xác định phiên Breakout chuẩn đại diện bằng Sbar, LSbar hoặc Combo Sbar.
    Điều kiện VSA cốt lõi (theo 'TTCKVN - Cuộc chơi của các tay chơi thực thụ'):
    1. Có nền giá tích lũy (Nền 1 hoặc Nền 2 >= 5 phiên).
    2. Có nhịp rũ bỏ (Shakeout) và kiệt cung (Volume Dry-Up <= 0.88x TB10).
    3. Thanh bùng nổ là Sbar hoặc Combo Sbar:
       - Sbar đơn lẻ:
         + Biên độ (High - Low) >= 1.20 * avg_range20 (vượt bình quân 20% - 50%)
         + Đóng cửa ở nửa trên (> 50% thân nến)
         + Volume >= 1.25x TB10
         + Tăng giá >= 2.0%
       - Combo Sbar (gộp 2 nến liên tiếp):
         + Biên độ gộp (max(H1, H2) - min(L1, L2)) >= 1.30 * avg_range20
         + Đóng cửa C2 ở nửa trên (> 50% biên độ gộp)
         + Khối lượng bùng nổ ở một trong 2 nến >= 1.20x TB10
         + Mức tăng lũy kế 2 phiên >= 2.5%
    """
    if df is None or len(df) < 25:
        return False, "Không đủ dữ liệu", {}
        
    curr_idx = (len(df) - 1) if idx is None else idx
    row = df.iloc[curr_idx]
    prev = df.iloc[curr_idx - 1] if curr_idx > 0 else row
    prev2 = df.iloc[curr_idx - 2] if curr_idx > 1 else prev
    
    close = float(row['close'])
    prev_close = float(prev['close'])
    prev2_close = float(prev2['close'])
    high = float(row['high'])
    low = float(row['low'])
    vol = float(row['volume'])
    avg_v10 = float(row['avg_vol10']) if 'avg_vol10' in row else vol
    
    # Tính avg_range20
    candle_len = high - low
    ranges = (df['high'] - df['low']).values
    avg_range20 = np.mean(ranges[max(0, curr_idx - 20):curr_idx]) if curr_idx >= 5 else candle_len
    
    # 1. Kiểm tra Sbar đơn lẻ
    spread_ratio = candle_len / (avg_range20 + 1e-9)
    close_pos = (close - low) / (candle_len + 1e-9) if candle_len > 0 else 0.5
    chg_pct = (close - prev_close) / (prev_close + 1e-9) * 100.0
    vol_r10 = vol / (avg_v10 + 1e-9)
    
    is_single_sbar = (spread_ratio >= 1.20) and (close_pos >= 0.55) and (vol_r10 >= 1.25) and (chg_pct >= 2.0)
    
    # 2. Kiểm tra Combo Sbar (gộp 2 nến)
    combo_high = max(high, float(prev['high']))
    combo_low = min(low, float(prev['low']))
    combo_len = combo_high - combo_low
    combo_spread_ratio = combo_len / (avg_range20 + 1e-9)
    combo_close_pos = (close - combo_low) / (combo_len + 1e-9) if combo_len > 0 else 0.5
    combo_chg = (close - prev2_close) / (prev2_close + 1e-9) * 100.0
    combo_vol_ok = (vol_r10 >= 1.20) or (float(prev['volume']) / (float(prev.get('avg_vol10', vol)) + 1e-9) >= 1.20)
    
    is_combo_sbar = (combo_spread_ratio >= 1.30) and (combo_close_pos >= 0.55) and combo_vol_ok and (combo_chg >= 2.5) and (chg_pct > 0)
    
    # 3. Kiểm tra nền giá hỗ trợ phía trước (có nền >= 5 phiên, rũ bỏ & kiệt cung)
    lookback_base = df.iloc[max(0, curr_idx - 20):curr_idx]
    has_base = len(lookback_base) >= 5
    min_v_ratio = np.min(lookback_base['volume'] / (lookback_base['avg_vol10'] + 1e-9)) if has_base else 1.0
    has_vdu = (min_v_ratio <= 0.88)
    
    if (is_single_sbar or is_combo_sbar) and has_base and has_vdu:
        sbar_type = "Sbar Đơn Lẻ" if is_single_sbar else "Combo Sbar 2 Phiên"
        spread_val = spread_ratio if is_single_sbar else combo_spread_ratio
        reason = f"Breakout xác nhận bằng {sbar_type} (Biên độ {spread_val:.2f}x TB20, Vol nổ, nền trước kiệt cung {min_v_ratio:.2f}x)"
        return True, sbar_type, {"reason": reason, "is_single": is_single_sbar, "is_combo": is_combo_sbar, "spread_ratio": spread_val}
        
    return False, "Chưa thỏa mãn Sbar/Combo Sbar Breakout", {}

def check_rbar_exit_warning(df: pd.DataFrame, buy_date: str = None, buy_price: float = None) -> tuple[bool, str, dict]:
    """
    Xác định thanh Reversal Bar (Rbar) đảo chiều thoát hàng / cắt lỗ.
    Theo quy chuẩn VSA: Rbar đóng cửa THỦNG dưới True Range của thanh LSbar tăng trước đó.
    True Range của LSbar = [min(Low, prev_Close), max(High, prev_Close)]
    => Khi Rbar xuất hiện: Bẻ gãy hoàn toàn xu hướng Swing Up => KÍCH HOẠT CẮT LỖ / THOÁT HÀNG.
    """
    if df is None or len(df) < 10:
        return False, "Không đủ dữ liệu", {}
        
    curr_idx = len(df) - 1
    curr_row = df.iloc[curr_idx]
    curr_close = float(curr_row['close'])
    
    # Tìm thanh LSbar tăng giá gần nhất (trong vòng 25 phiên trở lại)
    last_lsbar_idx = None
    ranges = (df['high'] - df['low']).values
    avg_range20 = np.mean(ranges[-20:]) if len(ranges) >= 20 else 1.0
    
    for lb in range(curr_idx - 1, max(0, curr_idx - 25), -1):
        b_row = df.iloc[lb]
        b_prev = df.iloc[lb - 1] if lb > 0 else b_row
        b_close = float(b_row['close'])
        b_prev_close = float(b_prev['close'])
        b_len = float(b_row['high']) - float(b_row['low'])
        b_pos = (b_close - float(b_row['low'])) / (b_len + 1e-9) if b_len > 0 else 0.5
        b_chg = (b_close - b_prev_close) / (b_prev_close + 1e-9) * 100.0
        b_vr = float(b_row['volume']) / (float(b_row['avg_vol10']) + 1e-9)
        
        # Tiêu chuẩn Sbar tăng
        if (b_len >= 1.15 * avg_range20) and (b_pos >= 0.50) and (b_chg >= 1.8) and (b_vr >= 1.15):
            last_lsbar_idx = lb
            break
            
    if last_lsbar_idx is not None:
        lsbar_row = df.iloc[last_lsbar_idx]
        prev_lsbar = df.iloc[last_lsbar_idx - 1] if last_lsbar_idx > 0 else lsbar_row
        
        # True Range của LSbar (tính cả gap)
        true_low = min(float(lsbar_row['low']), float(prev_lsbar['close']))
        true_high = max(float(lsbar_row['high']), float(prev_lsbar['close']))
        lsbar_date = str(lsbar_row['time'])[:10]
        
        # Rbar đảo chiều: Giá đóng cửa hiện tại thấp hơn True Range Low của LSbar
        if curr_close < true_low:
            reason = (
                f"🚨 CẢNH BÁO RBAR ĐẢO CHIỀU: Giá đóng cửa ({curr_close:.2f}) thủng dưới True Range đáy ({true_low:.2f}) "
                f"của thanh LSbar tăng ngày {lsbar_date}! Đảo chiều Swing Up -> KÍCH HOẠT THOÁT HÀNG / BÁN CẮT LỖ TOÀN BỘ!"
            )
            return True, reason, {"lsbar_date": lsbar_date, "true_low": true_low, "true_high": true_high}
            
    return False, "Chưa xuất hiện Rbar đảo chiều", {}

def check_no_supply_and_test_cung(df: pd.DataFrame, idx: int = None) -> tuple[bool, bool, str, dict]:
    """
    Kiểm tra sự xuất hiện của nến No Supply và nến Test Cung (VSA chuẩn hóa).
    Đặc trưng tại Điểm Cược (C1, C2...):
    - Nến No Supply: Thân nến hẹp, dao động nhỏ, Vol teo tóp kiệt quệ <= 0.85x TB10 (chứng minh cạn lực bán).
    - Nến Test Cung: Nhúng sâu trong phiên rũ bỏ rồi rút chân đóng cửa nửa trên (close_pos >= 0.50), Vol cực thấp <= 0.85x TB10.
    """
    if df is None or len(df) < 15:
        return False, False, "Không đủ dữ liệu", {}
        
    curr_idx = (len(df) - 1) if idx is None else idx
    lookback = min(curr_idx, 3) # Xét trong 3 phiên gần nhất của nền
    
    has_no_supply = False
    has_test_cung = False
    ns_date = ""
    tc_date = ""
    
    for i in range(curr_idx, max(0, curr_idx - lookback), -1):
        row = df.iloc[i]
        prev = df.iloc[i-1] if i > 0 else row
        
        c = float(row['close'])
        o = float(row['open'])
        h = float(row['high'])
        l = float(row['low'])
        v = float(row['volume'])
        prev_v = float(prev['volume'])
        avg_v10 = float(row['avg_vol10']) if 'avg_vol10' in row else v
        
        c_len = h - l
        c_pos = (c - l) / (c_len + 1e-9) if c_len > 0 else 0.5
        chg = (c - float(prev['close'])) / (float(prev['close']) + 1e-9) * 100.0
        vr = v / (avg_v10 + 1e-9)
        
        # Tiêu chuẩn No Supply: thân hẹp, biên độ hẹp (-1.8% <= chg <= 0.8%), vol cạn kiệt <= 0.88x TB10
        is_ns = (vr <= 0.88) and (-1.8 <= chg <= 0.8) and (v <= prev_v * 1.15) and (c_pos <= 0.65)
        if is_ns and not has_no_supply:
            has_no_supply = True
            ns_date = str(row['time'])[:10] if 'time' in row else f"T-{curr_idx - i}"
            
        # Tiêu chuẩn Test Cung: nhúng xuống rồi rút chân đóng cao (c_pos >= 0.50), vol cạn <= 0.88x TB10
        is_tc = (vr <= 0.88) and (c_pos >= 0.50) and (chg >= -1.2) and (h > l)
        if is_tc and not has_test_cung:
            has_test_cung = True
            tc_date = str(row['time'])[:10] if 'time' in row else f"T-{curr_idx - i}"

    notes = []
    if has_no_supply: notes.append(f"No Supply ({ns_date})")
    if has_test_cung: notes.append(f"Test Cung ({tc_date})")
    
    has_pair = has_no_supply and has_test_cung
    desc = " + ".join(notes) if notes else "Nền nén chặt kiệt cung"
    return has_no_supply, has_test_cung, desc, {"has_pair": has_pair, "ns_date": ns_date, "tc_date": tc_date}

def check_tennis_ball_action(df: pd.DataFrame, idx: int = None) -> tuple[bool, str, dict]:
    """
    Xác định hành vi QUẢ BÓNG TENNIS (Tennis Ball Action).
    ĐỊNH NGHĨA CHUẨN XÁC:
    Quả bóng Tennis CHỈ XUẤT HIỆN SAU KHI ĐÃ CÓ ĐIỂM B1 THÀNH CÔNG!
    Sau khi cổ phiếu đã có nhịp nổ dứt khoát (B1), thị trường chung có biến cố khiến cổ phiếu bị điều chỉnh rung lắc mạnh.
    Nhưng ngay khi thị trường cân bằng ổn định, cổ phiếu LẬP TỨC BẬT TĂNG MẠNH NGAY (tăng >= 2.0%, đóng cửa nửa trên,
    có thể vượt đỉnh luôn chỉ trong 1-2 phiên).
    """
    if df is None or len(df) < 20:
        return False, "Không đủ dữ liệu", {}
        
    curr_idx = (len(df) - 1) if idx is None else idx
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    vols = df['volume'].values
    avg_v10s = df['avg_vol10'].values if 'avg_vol10' in df.columns else vols
    
    # 1. Tìm phiên Breakout (B1) gần nhất trong 25 phiên qua
    last_bo_idx = None
    for lb in range(curr_idx - 1, max(0, curr_idx - 25), -1):
        p_c = closes[max(0, lb - 1)]
        b_c = closes[lb]
        b_chg = (b_c - p_c) / (p_c + 1e-9) * 100.0
        b_vr = vols[lb] / (avg_v10s[lb] + 1e-9)
        if (b_chg >= 2.2 and b_vr >= 1.25) or (b_vr >= 1.7 and b_chg >= 1.5):
            last_bo_idx = lb
            break
            
    if last_bo_idx is None:
        return False, "Chưa có nhịp nổ B1 làm mốc", {}
        
    bars_since_bo = curr_idx - last_bo_idx
    if bars_since_bo < 2 or bars_since_bo > 20:
        return False, f"Thời gian sau nổ ({bars_since_bo} phiên) ngoài khung Tennis Ball", {}
        
    bo_high = highs[last_bo_idx]
    bo_close = closes[last_bo_idx]
    
    # 2. Kiểm tra có nhịp điều chỉnh / rũ bỏ giữa chừng
    middle_lows = lows[last_bo_idx + 1 : curr_idx]
    has_pullback = False
    if len(middle_lows) > 0:
        min_mid_low = np.min(middle_lows)
        has_pullback = (min_mid_low < bo_close * 1.01)
    else:
        has_pullback = True
        
    # 3. Kiểm tra phiên hiện tại bật tăng mạnh (Quả bóng nảy)
    curr_c = closes[curr_idx]
    prev_c = closes[curr_idx - 1]
    curr_chg = (curr_c - prev_c) / (prev_c + 1e-9) * 100.0
    c_len = highs[curr_idx] - lows[curr_idx]
    c_pos = (curr_c - lows[curr_idx]) / (c_len + 1e-9) if c_len > 0 else 0.5
    curr_vr = vols[curr_idx] / (avg_v10s[curr_idx] + 1e-9)
    
    is_tennis_bounce = (curr_chg >= 2.0) and (c_pos >= 0.60) and (curr_vr >= 0.90) and has_pullback
    tests_breakout_high = (curr_c >= bo_high * 0.985)
    
    if is_tennis_bounce and (tests_breakout_high or curr_chg >= 2.8):
        reason = f"Bật tăng Quả Bóng Tennis (Sau nổ B1 {bars_since_bo} phiên, nảy lại +{curr_chg:.1f}%, Vol {curr_vr:.1f}x TB10)"
        return True, reason, {"bars_since_bo": bars_since_bo, "bounce_chg": curr_chg, "bo_high": bo_high}
        
    return False, "Chưa xuất hiện nhịp nảy Quả Bóng Tennis", {}

def score_bdi_stock(symbol: str, target_date_str: str = None) -> dict:
    """
    Evaluates stock using the VSA Ông Bình Design Index (BDI) (0 - 100 points)
    and identifies candidate buy points with progressive stage cycle (C1/P1/B1 -> C2/P2/B2...).
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
    
    # 1. Nhận diện loại điểm mua VSA & Chu kỳ nhịp tăng (Stage n)
    point_name = "Tích Lũy Nền (Chưa có điểm mua)"
    point_code = "NONE"
    
    # Kiểm tra Thuật toán số 2: Xác thực Nền Mới Sau Nhịp Nổ
    is_base_valid, base_desc, base_meta = check_new_base_after_breakout(df, idx=len(df)-1)
    
    # Kiểm tra cặp nến No Supply & Test Cung
    has_ns, has_tc, cung_desc, cung_meta = check_no_supply_and_test_cung(df, idx=len(df)-1)
    
    # Kiểm tra hành vi Quả bóng Tennis (chỉ xuất hiện sau khi đã có nổ B1)
    is_tennis, tennis_desc, tennis_meta = check_tennis_ball_action(df, idx=len(df)-1)
    
    # Breakout B: Đại diện bởi Sbar, LSbar hoặc Combo Sbar
    is_sbar_bo, sbar_name, sbar_meta = check_sbar_breakout(df, idx=len(df)-1)
    is_vol_surge = (vol >= 2.5 * avg_v10) and (avg_v10 >= 50000) and (chg_pct >= 1.5) and (close_pos >= 0.70)
    is_breakout = is_sbar_bo or ((chg_pct >= 2.3) and (vol_r10 >= 1.3) and (close_pos >= 0.70) and (close >= ma20)) or is_vol_surge
    
    # Pivot P: Đẩy nền bám sát MA20, vol nhú 0.85 - 2.2x, nến xanh tăng nhẹ-khá
    is_pivot = (0.6 <= chg_pct <= 4.0) and (-2.0 <= dist_ma20 <= 3.8) and (vol_r10 >= 0.85) and (close_pos >= 0.55) and obv_up
    
    # Cược C: Trong nền nén chặt, có No Supply hoặc Test Cung hoặc Thuật toán số 2
    is_cuoc = bool(is_base_valid and (abs(dist_ma20) <= 3.5) and (vol_r10 <= 0.90) and (chg_pct >= -2.0))
    
    # Xác định số thứ tự chu kỳ (Stage: 1, 2, 3...)
    stage_num = 1
    if base_meta.get("base_type") == "BASE2_CUOC" or is_tennis:
        stage_num = 2
    elif base_meta.get("bars_since_bo", 0) >= 15:
        stage_num = 2
        
    if is_vol_surge:
        point_name = f"Điểm Đột Biến Thể Tích Sớm (Volume Surge B{stage_num})"
        point_code = f"B{stage_num}"
    elif is_sbar_bo:
        point_name = f"Điểm Nổ Breakout ({sbar_name} B{stage_num})"
        point_code = f"B{stage_num}"
    elif is_breakout:
        point_name = f"Điểm Nổ Breakout (B{stage_num})"
        point_code = f"B{stage_num}"
    elif is_tennis:
        point_name = f"Quả Bóng Tennis Bật Tăng (Sau Nổ B{stage_num-1 if stage_num > 1 else 1})"
        point_code = f"P{stage_num}" # Đẩy nền nảy vượt đỉnh
    elif is_pivot:
        point_name = f"Điểm Đẩy Nền Pivot (P{stage_num})"
        point_code = f"P{stage_num}"
    elif is_cuoc:
        c_detail = f" ({cung_desc})" if (has_ns or has_tc) else " (Nén Chặt Kiệt Cung)"
        if stage_num >= 2:
            point_name = f"Điểm Cược Nền {stage_num}{c_detail}"
        else:
            point_name = f"Điểm Mua Cược Nền (C{stage_num}){c_detail}"
        point_code = f"C{stage_num}"
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
    
    # 3. Tính toán Lộ trình 3 Bước Giải Ngân (C: 50% -> P: 50% -> B: Margin) & Điểm chặn hòa vốn
    recent_20 = df.iloc[max(0, len(df)-20):]
    recent_high = float(recent_20['high'].max())
    recent_low = float(recent_20['low'].min())
    
    c_entry_price = round(close, 2)
    p_entry_price = round(ma20 * 1.015, 2)
    b_entry_price = round(recent_high * 1.005, 2)
    
    # Hard stop khi mua C: Đáy nến thấp nhất gần đây
    c_hard_stop = round(min(low, recent_low), 2)
    c_risk_pct = round((c_hard_stop - close) / (close + 1e-9) * 100, 1)
    
    # Điểm chặn hòa vốn:
    if point_code.startswith("B"):
        be_stop = round((row['open'] + close) / 2.0, 2)
        be_desc = f"Bảo vệ 50% thân nến nổ B{stage_num} ({be_stop})"
    elif point_code.startswith("P"):
        be_stop = round(c_entry_price, 2)
        be_desc = f"Dời Stop Loss lên giá hòa vốn C{stage_num} ({be_stop})"
    else:
        be_stop = round(c_hard_stop, 2)
        be_desc = f"Cắt lỗ cứng đáy nến/đáy nền C{stage_num} ({be_stop})"
        
    capital_plan = {
        "stage": stage_num,
        "entry_c_price": c_entry_price,
        "entry_c_desc": f"C{stage_num}: 50% Tiền Mặt (Cược trong nền)",
        "entry_p_price": p_entry_price,
        "entry_p_desc": f"P{stage_num}: 50% Tiền Mặt Còn Lại (Đẩy nền Pocket nhú MA20 -> Đủ 100% tiền)",
        "entry_b_price": b_entry_price,
        "entry_b_desc": f"B{stage_num}: Mở Margin Nếu Cần (Sbar nổ vượt đỉnh)",
        "hard_stop": c_hard_stop,
        "hard_stop_pct": c_risk_pct,
        "breakeven_stop": be_stop,
        "breakeven_desc": be_desc
    }
    
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
        "stage": stage_num,
        "capital_plan": capital_plan,
        "is_tennis_ball": bool(is_tennis),
        "tennis_ball_meta": tennis_meta,
        "has_no_supply": bool(has_ns),
        "has_test_cung": bool(has_tc),
        "cung_desc": cung_desc,
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
        p_code = "C1"
        c_plan = {}
    else:
        cur_p = float(bdi_res.get("close", 10.0))
        cur_bdi = int(bdi_res.get("bdi_score", 50))
        point_name = bdi_res.get("point_name", "Chờ tín hiệu")
        p_code = bdi_res.get("point_code", "C1")
        c_plan = bdi_res.get("capital_plan", {})
        
    w_id = f"WATCH_{sym}_{int(time.time())}"
    hard_stop = float(c_plan.get("hard_stop") or (cur_p * 0.96))
    be_stop = float(c_plan.get("breakeven_stop") or hard_stop)
    
    new_item = {
        "id": w_id,
        "symbol": sym,
        "added_date": datetime.now().strftime("%Y-%m-%d"),
        "entry_price": cur_p,
        "current_price": cur_p,
        "today_chg_pct": bdi_res.get("chg_pct", 0.0) if bdi_res.get("status") != "error" else 0.0,
        "pnl_pct": 0.0,
        "bdi_score": cur_bdi,
        "stage_code": p_code,
        "point_name": point_name,
        "hard_stop": hard_stop,
        "breakeven_stop": be_stop,
        "capital_plan": c_plan,
        "status_note": notes or f"Khởi tạo {p_code}: 50% Tiền Mặt (Chặn lỗ {hard_stop:.2f})",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    watchlist.insert(0, new_item)
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)
        
    return {"status": "success", "message": f"Đã thêm {sym} vào Danh Mục Theo Dõi!", "data": new_item}

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

def sync_active_living_watchlist(candidates_list: list = None, target_date_str: str = None) -> dict:
    """
    Quản lý Danh Mục Theo Dõi Động (Smart Living Watchlist):
    1. Tự động nạp: Cổ phiếu đạt điểm C1, C2... hôm nay -> tự động nạp vào.
    2. Tự động thăng cấp: C1 -> P1 -> B1 -> C2...
    3. Tự động đào thải (Auto-Purge):
       + Thủng giá cắt lỗ cứng hoặc điểm chặn hòa vốn.
       + Thủng 50% thân nến nổ Zero-Đỉnh (khi đang ở B).
       + Xuất hiện Rbar đảo chiều hoặc vi phạm rủi ro lớn.
       + Gãy MA50 & MA20 (Downtrend).
    """
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    watchlist = load_watchlist_positions()
    active_items = []
    purged_items = []
    seen_syms = set()
    
    # 1. Rà soát và cập nhật / đào thải các cổ phiếu đang có trong danh mục
    for it in watchlist:
        sym = it.get("symbol", "").upper().strip()
        if not sym or sym in seen_syms:
            continue
        seen_syms.add(sym)
        
        bdi_res = score_bdi_stock(sym, target_date_str=target_date_str)
        if not bdi_res or bdi_res.get("status") == "error":
            active_items.append(it)
            continue
            
        curr_close = float(bdi_res.get("close", it.get("current_price", 0)))
        entry_price = float(it.get("entry_price", curr_close))
        curr_bdi = float(bdi_res.get("bdi_score", 0))
        p_code = bdi_res.get("point_code", "NONE")
        c_plan = bdi_res.get("capital_plan", {})
        
        hard_stop = float(it.get("hard_stop") or c_plan.get("hard_stop") or (entry_price * 0.96))
        be_stop = float(it.get("breakeven_stop") or c_plan.get("breakeven_stop") or hard_stop)
        
        # Tiêu chí Auto-Purge
        is_purged = False
        purge_reason = ""
        
        # A. Thủng điểm chặn hòa vốn / cắt lỗ cứng
        effective_stop = be_stop if it.get("stage_code", "").startswith(("P", "B")) else hard_stop
        if curr_close < effective_stop * 0.995:
            is_purged = True
            purge_reason = f"Đóng cửa ({curr_close:.2f}) thủng điểm chặn ({effective_stop:.2f})"
            
        # B. Nếu đang ở B mà vi phạm Zero-Đỉnh (gãy 50% thân nến nổ)
        zero_crit = next((c for c in bdi_res.get("criteria", []) if "Zero-Đỉnh" in c.get("name", "")), None)
        if not is_purged and it.get("stage_code", "").startswith("B") and zero_crit and not zero_crit.get("passed", True):
            is_purged = True
            purge_reason = f"Vi phạm Kỷ luật Zero-Đỉnh ({zero_crit.get('desc', 'Gãy 50% thân nến nổ')})"
            
        # C. Xuất hiện Rbar đảo chiều
        try:
            s_df = get_prepared_stock_df(sym, target_date_str)
            if s_df is not None and not s_df.empty:
                is_rbar, rbar_msg, _ = check_rbar_exit_warning(s_df)
                if not is_purged and is_rbar:
                    is_purged = True
                    purge_reason = "Xuất hiện thanh Rbar đảo chiều dòng tiền"
        except Exception:
            pass
            
        if is_purged:
            purged_items.append({
                "symbol": sym,
                "purge_date": str(bdi_res.get("date", datetime.now().strftime("%Y-%m-%d"))),
                "last_price": curr_close,
                "entry_price": entry_price,
                "pnl_pct": round((curr_close - entry_price) / (entry_price + 1e-9) * 100, 2),
                "reason": purge_reason
            })
            continue
            
        # Nâng cấp trạng thái nếu xuất hiện điểm mua mới
        curr_stage = it.get("stage_code", "C1")
        status_note = it.get("status_note", "Duy trì xu hướng tăng chuẩn")
        if p_code.startswith("B") and not curr_stage.startswith("B"):
            curr_stage = p_code
            be_stop = float(c_plan.get("breakeven_stop", entry_price))
            status_note = f"Thăng cấp {p_code}: Mở Margin nếu cần (Bảo vệ Zero-Đỉnh)"
        elif p_code.startswith("P") and curr_stage.startswith("C"):
            curr_stage = p_code
            be_stop = entry_price # Dời Stop loss lên giá hòa vốn C1
            status_note = f"Thăng cấp {p_code}: Đủ 100% tiền mặt (Dời Stop Loss lên hòa vốn)"
        elif p_code.startswith("C") and int(p_code[1:] if p_code[1:].isdigit() else 1) > int(curr_stage[1:] if curr_stage[1:].isdigit() else 1):
            curr_stage = p_code
            status_note = f"Setup nền mới {p_code}: Cược 50% tiền mặt"
            
        pnl_pct = round((curr_close - entry_price) / (entry_price + 1e-9) * 100, 2)
        
        it.update({
            "current_price": curr_close,
            "today_chg_pct": bdi_res.get("chg_pct", 0.0),
            "pnl_pct": pnl_pct,
            "bdi_score": curr_bdi,
            "stage_code": curr_stage,
            "point_name": bdi_res.get("point_name", ""),
            "hard_stop": hard_stop,
            "breakeven_stop": be_stop,
            "capital_plan": c_plan,
            "status_note": status_note,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        active_items.append(it)
        
    # 2. Tự động nạp các cổ phiếu C1, C2... mới từ kết quả quét hôm nay
    new_added_count = 0
    if candidates_list:
        for cand in candidates_list:
            sym = cand.get("symbol", "").upper().strip()
            p_code = cand.get("point_code", "")
            if not sym or sym in seen_syms:
                continue
                
            if p_code.startswith(("C", "P")):
                seen_syms.add(sym)
                c_price = float(cand.get("close", 0.0))
                c_plan = cand.get("capital_plan", {})
                hard_stop = float(c_plan.get("hard_stop") or (c_price * 0.96))
                be_stop = float(c_plan.get("breakeven_stop") or hard_stop)
                
                new_item = {
                    "id": f"WATCH_{sym}_{int(time.time())}",
                    "symbol": sym,
                    "added_date": str(cand.get("date", datetime.now().strftime("%Y-%m-%d"))),
                    "entry_price": c_price,
                    "current_price": c_price,
                    "today_chg_pct": cand.get("chg_pct", 0.0),
                    "pnl_pct": 0.0,
                    "bdi_score": float(cand.get("bdi_score", cand.get("score", 70))),
                    "stage_code": p_code,
                    "point_name": cand.get("point_name", cand.get("desc", "")),
                    "hard_stop": hard_stop,
                    "breakeven_stop": be_stop,
                    "capital_plan": c_plan,
                    "status_note": f"Khởi tạo {p_code}: 50% Tiền Mặt (Chặn lỗ {hard_stop:.2f})",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                active_items.insert(0, new_item)
                new_added_count += 1
                
    active_items.sort(key=lambda x: (x.get("stage_code", ""), x.get("bdi_score", 0)), reverse=True)
    
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(active_items, f, ensure_ascii=False, indent=2)
        
    return {
        "status": "success",
        "total_active": len(active_items),
        "newly_added": new_added_count,
        "purged_count": len(purged_items),
        "purged_items": purged_items,
        "active_watchlist": active_items
    }

def evaluate_watchlist_signals() -> list:
    """Evaluates real-time buy signals for all active living watchlist items."""
    sync_res = sync_active_living_watchlist()
    return sync_res.get("active_watchlist", [])

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
        
        # Kiểm tra cảnh báo Rbar đảo chiều (Thủng True Range của LSbar tăng gần nhất)
        is_rbar, rbar_alert_msg, rbar_meta = check_rbar_exit_warning(df, buy_date=buy_date, buy_price=buy_price)
        
        # --- THỨ TỰ PHÂN CẤP CẢNH BÁO RRBDI ---
        # CẤP 3: BÁO ĐỘNG ĐỎ (Xuất hiện Rbar đảo chiều HOẶC Thủng Low nến mua HOẶC gãy 3 phiên MA10/MA20)
        if is_rbar:
            rrbdi_level = "RED"
            rrbdi_badge = "🚨 CẤP BÁO ĐỎ (Rbar Đảo Chiều)"
            rrbdi_alert = rbar_alert_msg
        elif broke_low:
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
