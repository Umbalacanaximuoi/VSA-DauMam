import os
import sys
import struct
import time
import pandas as pd
import numpy as np
from datetime import datetime
from vnstock import Quote, Trading

def safe_print(*args):
    try:
        cleaned = [str(arg).encode('cp1252', errors='replace').decode('cp1252', errors='replace') for arg in args]
        print(*cleaned)
    except Exception:
        try:
            cleaned = [str(arg).encode('ascii', errors='ignore').decode('ascii') for arg in args]
            print(*cleaned)
        except Exception:
            pass

def calculate_rsi(df, period=14):
    if len(df) < period:
        return pd.Series([50.0] * len(df))
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(df, fast=12, slow=26, signal=9):
    if len(df) < slow:
        return pd.Series([0.0] * len(df)), pd.Series([0.0] * len(df)), pd.Series([0.0] * len(df))
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    return macd_line, signal_line, macd_hist

def load_stock_data(symbol: str, target_date_str: str = None) -> pd.DataFrame:
    """
    Attempts to load stock data from vnstock API,
    local CSV (data/{symbol}.csv), or falls back to Metakit binary database.
    """
    symbol = symbol.upper().strip()
    
    target_dt = None
    if target_date_str:
        try:
            target_dt = pd.to_datetime(target_date_str, format="%Y-%m-%d")
        except Exception:
            pass
            
    # 1. Try vnstock API (Primary online source)
    try:
        safe_print(f"Fetching {symbol} data from vnstock 4.x API")
        from vnstock.ui import Market
        mkt = Market()
        base_dt = datetime.now()
        if target_date_str:
            try:
                base_dt = pd.to_datetime(target_date_str, format="%Y-%m-%d")
            except Exception:
                pass
        today_str = base_dt.strftime("%Y-%m-%d")
        start_date = (base_dt - pd.Timedelta(days=350)).strftime("%Y-%m-%d")
        df = mkt.equity(symbol).ohlcv(start=start_date, end=today_str, interval="1D")
        if df is not None and not df.empty:
            df = df[['time', 'open', 'high', 'low', 'close', 'volume']].copy()
            df['time'] = df['time'].astype(str).str.slice(0, 10)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['close', 'volume']).reset_index(drop=True)
            
            # Check if target date is before the start of vnstock data
            if target_dt is not None and not df.empty:
                first_date = pd.to_datetime(df['time'].iloc[0])
                if target_dt < first_date:
                    safe_print(f"Target date {target_date_str} is before vnstock data start ({df['time'].iloc[0]}). Bypassing vnstock to load history.")
                    raise ValueError("Target date is before vnstock data range")
                    
            return df
    except Exception as e:
        safe_print(f"Vnstock 4.x API failed for {symbol}: {e}. Trying local CSV.")

    # 2. Try Local CSV File (Secondary source)
    base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
    data_dir = os.path.join(base_dir, 'data')
    if not os.path.exists(data_dir) and getattr(sys, 'frozen', False):
        alt_data = os.path.join(getattr(sys, '_MEIPASS', base_dir), 'data')
        if os.path.exists(alt_data):
            data_dir = alt_data
    local_file = os.path.join(data_dir, f"{symbol}.csv")
    
    if os.path.exists(local_file):
        try:
            safe_print(f"Loading local data for {symbol} from {local_file}")
            df = pd.read_csv(local_file)
            
            # Normalize column names to lowercase
            df.columns = [col.lower().strip() for col in df.columns]
            
            # Map common columns
            rename_map = {}
            for col in df.columns:
                if col in ['ticker', 'symbol', 'ma']:
                    rename_map[col] = 'symbol'
                elif col in ['date/time', 'datetime', 'date', 'time', 'timestamp']:
                    rename_map[col] = 'time'
                elif col in ['open', 'op']:
                    rename_map[col] = 'open'
                elif col in ['high', 'hi']:
                    rename_map[col] = 'high'
                elif col in ['low', 'lo']:
                    rename_map[col] = 'low'
                elif col in ['close', 'cl']:
                    rename_map[col] = 'close'
                elif col in ['volume', 'vol', 'v']:
                    rename_map[col] = 'volume'
                    
            df = df.rename(columns=rename_map)
            
            # Validate required columns
            required = ['time', 'open', 'high', 'low', 'close', 'volume']
            for req in required:
                if req not in df.columns:
                    raise ValueError(f"Missing required column: {req}")
                    
            # Ensure proper types
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            df = df.dropna(subset=['close', 'volume'])
            # Sort by time
            df = df.sort_values(by='time').reset_index(drop=True)
            return df
        except Exception as e:
            safe_print(f"Error loading local file: {e}. Trying Metakit database.")
            
    # 3. Try Metakit Binary Database (.dat) (Fallback source)
    metakit_file = os.path.join(r"C:\MetakitData\AmiBroker\EOD\stock", f"{symbol}.dat")
    if not os.path.exists(metakit_file):
        metakit_file = os.path.join(r"C:\MetakitData\AmiBroker\EOD\index", f"{symbol}.dat")
        
    if os.path.exists(metakit_file):
        try:
            safe_print(f"Loading data for {symbol} from Metakit database: {metakit_file}")
            with open(metakit_file, "rb") as f:
                header = f.read(32)
                if len(header) >= 32:
                    num_recs = struct.unpack("<I", header[:4])[0]
                    
                    dates = []
                    opens = []
                    highs = []
                    lows = []
                    closes = []
                    volumes = []
                    
                    for _ in range(num_recs):
                        rec = f.read(32)
                        if len(rec) < 32:
                            break
                        date_int, pad, open_p, high_p, low_p, close_p, vol, val = struct.unpack("<IIfffffI", rec)
                        
                        # Format YYYYMMDD to YYYY-MM-DD
                        date_str = f"{date_int // 10000}-{(date_int % 10000) // 100 :02d}-{date_int % 100 :02d}"
                        
                        dates.append(date_str)
                        opens.append(open_p)
                        highs.append(high_p)
                        lows.append(low_p)
                        closes.append(close_p)
                        volumes.append(vol)
                        
                    df = pd.DataFrame({
                        "time": dates,
                        "open": opens,
                        "high": highs,
                        "low": lows,
                        "close": closes,
                        "volume": volumes
                    })
                    
                    # Sort and clean
                    df = df.dropna(subset=['close', 'volume'])
                    df = df.sort_values(by='time').reset_index(drop=True)
                    if not df.empty:
                        return df
        except Exception as e:
            safe_print(f"Error reading Metakit data for {symbol}: {e}.")
            
    return pd.DataFrame()

def evaluate_stock_from_df(df: pd.DataFrame, symbol: str, target_date_str: str = None):
    """
    Evaluates the stock based on BinhGiaVSA.afl criteria:
    Core Criteria (Weight: 60%):
      1. Giá trên MA50 (Close >= MA50)
      2. Biên độ giá hẹp (H-L <= AvgRange20)
      3. MACD >= 0
      4. Xu hướng RSI (RSI > 50)
    Auxiliary Criteria (Weight: 40%):
      1. Thứ tự đường MA10 >= MA20 >= MA50
      2. Đường RSI >= smoothed MA (RSI >= EMA(RSI, 9))
      3. MACD >= Tín hiệu (MACD >= Signal)
      4. Độ cong MA20 hướng lên (MA20_slope > 0)
      5. Độ cong MA50 hướng lên (MA50_slope > 0)
      6. Các đường trung bình MA hội tụ (convergence <= 2%)
      7. Vol phiên hiện tại cạn kiệt (Volume < Vol MA10)
    """
STOCK_EVAL_CACHE = {}

def evaluate_stock_from_df(df: pd.DataFrame, symbol: str, target_date_str: str = None) -> dict:
    cache_key = (symbol, target_date_str)
    if cache_key in STOCK_EVAL_CACHE:
        return STOCK_EVAL_CACHE[cache_key]

    try:
        if df.empty or len(df) < 30:
            return {"error": f"Không đủ dữ liệu giao dịch cho cổ phiếu {symbol}."}
        
        # Clean any missing close or volume
        if 'ma10' not in df.columns:
            df = df.dropna(subset=['close', 'volume']).copy()
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            df['open'] = pd.to_numeric(df['open'], errors='coerce')
            df['high'] = pd.to_numeric(df['high'], errors='coerce')
            df['low'] = pd.to_numeric(df['low'], errors='coerce')
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
            
            df['ma10'] = df['close'].rolling(window=10).mean()
            df['ma20'] = df['close'].rolling(window=20).mean()
            df['ma50'] = df['close'].rolling(window=50).mean()
            df['ma100'] = df['close'].rolling(window=100).mean()
            df['ma200'] = df['close'].rolling(window=200).mean()
            
            df['range'] = df['high'] - df['low']
            df['avg_range20'] = df['range'].rolling(window=20).mean()
            
            df['avg_vol10'] = df['volume'].rolling(window=10).mean()
            df['avg_vol20'] = df['volume'].rolling(window=20).mean()
            
            macd_line, signal_line, macd_hist = calculate_macd(df)
            df['macd'] = macd_line
            df['macd_signal'] = signal_line
            
            df['rsi'] = calculate_rsi(df, period=14)
            df['rsi_smoothed'] = df['rsi'].ewm(span=9, adjust=False).mean()
            
            df['ma20_slope'] = df['ma20'] - df['ma20'].shift(1)
            df['ma50_slope'] = df['ma50'] - df['ma50'].shift(1)
            
            ma_max = df[['ma10', 'ma20', 'ma50']].max(axis=1)
            ma_min = df[['ma10', 'ma20', 'ma50']].min(axis=1)
            df['ma_convergence'] = (ma_max - ma_min) / (df['ma20'] + 1e-9)
        
        if 'price_change' not in df.columns:
            df['price_change'] = df['close'] - df['close'].shift(1)
            df['price_change_pct'] = (df['price_change'] / (df['close'].shift(1) + 1e-9)) * 100
        
        # Get latest values or filter by target date
        if target_date_str:
            try:
                target_dt = pd.to_datetime(target_date_str, format="%Y-%m-%d")
                df['parsed_time'] = pd.to_datetime(df['time'], errors='coerce')
                df_filtered = df[df['parsed_time'] <= target_dt]
                if df_filtered.empty:
                    return {"error": f"Không có dữ liệu giao dịch cho {symbol} trước ngày {target_date_str}."}
                work_df = df_filtered.copy()
            except Exception as ex:
                return {"error": f"Lỗi định dạng mốc thời gian '{target_date_str}': {str(ex)}"}
        else:
            work_df = df.copy()
            
        latest = work_df.iloc[-1]
        prev = work_df.iloc[-2] if len(work_df) > 1 else latest
        i = len(work_df) - 1
        
        price = float(latest['close'])
        prev_price = float(prev['close'])
        price_change = price - prev_price
        price_change_pct = (price_change / prev_price) * 100 if prev_price > 0 else 0.0
        
        # Calculate Core Criteria (Total Weight: 60 points)
        core_results = []
        
        # Core 1: Giá trên MA50
        c1_passed = bool(price >= latest['ma50'])
        c1_desc = f"Giá hiện tại ({price:,.2f}) nằm {'trên hoặc bằng' if c1_passed else 'dưới'} đường trung bình MA50 ({latest['ma50']:,.2f})"
        core_results.append({"name": "Giá trên MA50", "passed": c1_passed, "desc": c1_desc})
        
        # Core 2: Thứ tự đường MA10 >= MA20 >= MA50 (Hoán đổi lên chính)
        ma10_val = float(latest['ma10'])
        ma20_val = float(latest['ma20'])
        ma50_val = float(latest['ma50'])
        c2_passed = bool(ma10_val >= ma20_val and ma20_val >= ma50_val)
        c2_desc = f"Đường trung bình ngắn hạn nằm trên dài hạn (MA10: {ma10_val:,.2f} >= MA20: {ma20_val:,.2f} >= MA50: {ma50_val:,.2f})" if c2_passed else f"Các đường MA đang đan xen (MA10: {ma10_val:,.2f}, MA20: {ma20_val:,.2f}, MA50: {ma50_val:,.2f})"
        core_results.append({"name": "Thứ tự đường MA10/MA20/MA50", "passed": c2_passed, "desc": c2_desc})
        
        # Core 3: MACD >= 0
        macd_val = float(latest['macd'])
        c3_passed = bool(macd_val >= 0)
        c3_desc = f"Đường MACD ({macd_val:.3f}) nằm {'trên hoặc bằng' if c3_passed else 'dưới'} mức 0"
        core_results.append({"name": "MACD >= 0", "passed": c3_passed, "desc": c3_desc})
        
        # Core 4: Xu hướng RSI (RSI > 50)
        rsi_val = float(latest['rsi'])
        c4_passed = bool(rsi_val > 50)
        c4_desc = f"Chỉ số RSI ({rsi_val:.1f}) {'đạt xu hướng mạnh (>50)' if c4_passed else 'yếu (<=50)'}"
        core_results.append({"name": "Xu hướng RSI (RSI > 50)", "passed": c4_passed, "desc": c4_desc})
        
        # Core score calculation (out of 100)
        core_passed_count = sum(1 for r in core_results if r["passed"])
        core_score = (core_passed_count / len(core_results)) * 100
        
        # Calculate Auxiliary Criteria (Total Weight: 40 points)
        aux_results = []
        
        # Aux 1: Biên độ giá hẹp (Spread) (Hoán đổi xuống phụ)
        spread_val = float(latest['range'])
        avg_spread = float(latest['avg_range20'])
        a1_passed = bool(spread_val <= avg_spread)
        a1_desc = f"Biên độ giá phiên ({spread_val:,.2f}) {'đạt chuẩn hẹp' if a1_passed else 'rộng hơn'} trung bình 20 phiên ({avg_spread:,.2f})"
        aux_results.append({"name": "Biên độ giá hẹp (Spread)", "passed": a1_passed, "desc": a1_desc})
        
        # Aux 2: Đường RSI >= smoothed MA
        rsi_smoothed_val = float(latest['rsi_smoothed'])
        a2_passed = bool(rsi_val >= rsi_smoothed_val)
        a2_desc = f"Chỉ số RSI ({rsi_val:.1f}) nằm {'trên hoặc bằng' if a2_passed else 'dưới'} đường làm mượt EMA9 ({rsi_smoothed_val:.1f})"
        aux_results.append({"name": "Đường RSI >= Smoothed MA", "passed": a2_passed, "desc": a2_desc})
        
        # Aux 3: MACD >= tín hiệu
        sig_val = float(latest['macd_signal'])
        a3_passed = bool(macd_val >= sig_val)
        a3_desc = f"Đường MACD ({macd_val:.3f}) nằm {'trên hoặc bằng' if a3_passed else 'dưới'} đường Tín hiệu ({sig_val:.3f})"
        aux_results.append({"name": "MACD >= Tín hiệu", "passed": a3_passed, "desc": a3_desc})
        
        # Aux 4: Độ cong MA20 hướng lên
        ma20_slope_val = float(latest['ma20_slope'])
        a4_passed = bool(ma20_slope_val > 0)
        a4_desc = f"Đường MA20 đang hướng lên (độ dốc: +{ma20_slope_val:.3f})" if a4_passed else f"Đường MA20 đang đi ngang hoặc hướng xuống (độ dốc: {ma20_slope_val:.3f})"
        aux_results.append({"name": "Độ cong MA20 hướng lên", "passed": a4_passed, "desc": a4_desc})
        
        # Aux 5: Độ cong MA50 hướng lên
        ma50_slope_val = float(latest['ma50_slope'])
        a5_passed = bool(ma50_slope_val > 0)
        a5_desc = f"Đường MA50 đang hướng lên (độ dốc: +{ma50_slope_val:.3f})" if a5_passed else f"Đường MA50 đang đi ngang hoặc hướng xuống (độ dốc: {ma50_slope_val:.3f})"
        aux_results.append({"name": "Độ cong MA50 hướng lên", "passed": a5_passed, "desc": a5_desc})
        
        # Aux 6: Các đường trung bình MA hội tụ (Chenh lech <= 2%)
        converge_val = float(latest['ma_convergence'])
        a6_passed = bool(converge_val <= 0.02)
        a6_desc = f"Các đường MA đang hội tụ rất chặt chẽ (độ lệch: {(converge_val*100):.1f}% <= 2%)" if a6_passed else f"Các đường MA đang phân kỳ (độ lệch: {(converge_val*100):.1f}% > 2%)"
        aux_results.append({"name": "Đường trung bình MA hội tụ", "passed": a6_passed, "desc": a6_desc})
        
        # Aux 7: Vol phiên hiện tại cạn kiệt (< vol MA10)
        vol_val = float(latest['volume'])
        vol_ma10 = float(latest['avg_vol10'])
        a7_passed = bool(vol_val < vol_ma10)
        a7_desc = f"Khối lượng hiện tại ({vol_val:,.0f}) cạn kiệt dưới trung bình 10 phiên ({vol_ma10:,.0f})" if a7_passed else f"Khối lượng hiện tại ({vol_val:,.0f}) lớn hơn trung bình 10 phiên ({vol_ma10:,.0f})"
        aux_results.append({"name": "Vol cạn kiệt (< trung bình Vol 10 phiên)", "passed": a7_passed, "desc": a7_desc})
        
        # Aux score calculation (out of 100)
        aux_passed_count = sum(1 for r in aux_results if r["passed"])
        aux_score = (aux_passed_count / len(aux_results)) * 100
        
        # Final Score
        final_score = (core_score * 0.6) + (aux_score * 0.4)
        
        # Rating name based on 5 zones: Blue, Red, Yellow, Green, Purple
        if final_score <= 25:
            rating_color = "blue"
            rating_text = "Rất Yếu (Blue)"
        elif final_score <= 45:
            rating_color = "red"
            rating_text = "Yếu (Red)"
        elif final_score <= 54:
            rating_color = "yellow"
            rating_text = "Trung Bình (Yellow)"
        elif final_score <= 75:
            rating_color = "green"
            rating_text = "Mạnh (Green)"
        else:
            rating_color = "purple"
            rating_text = "Rất Mạnh (Purple)"
            
        # Define helper check functions based on "ĐIỂM MUA KHUYẾN NGHỊ CHO HỆ THỐNG VSA ÔNG BÌNH.docx"
        def is_invalid_idx(idx):
            if idx < 34 or idx >= len(work_df):
                return True
            row = work_df.iloc[idx]
            if pd.isna(row['ma10']) or pd.isna(row['ma20']) or pd.isna(row['ma50']) or pd.isna(row['macd']) or pd.isna(row['rsi']):
                return True
            return False

        def check_cuer_1_8_first(idx):
            if is_invalid_idx(idx) or idx < 1:
                return False
            row = work_df.iloc[idx]
            prev_row = work_df.iloc[idx-1]
            
            is_upbar = bool(row['close'] > prev_row['close'])
            ma_converged = bool(abs(row['ma10'] - row['ma20']) / (row['ma20'] + 1e-9) <= 0.017)
            narrow_range = bool((row['high'] - row['low']) <= row['avg_range20'])
            low_vol = bool(row['volume'] < row['avg_vol10'])
            rsi_ok = bool(row['rsi'] >= row['rsi_smoothed'])
            above_ma = bool(row['close'] >= row['ma20'] or row['close'] >= row['ma10'])
            
            return bool(is_upbar and ma_converged and narrow_range and low_vol and rsi_ok and above_ma)

        def check_cuer_1_8_subsequent(idx):
            if is_invalid_idx(idx) or idx < 1:
                return False
            row = work_df.iloc[idx]
            prev_row = work_df.iloc[idx-1]
            
            is_upbar = bool(row['close'] > prev_row['close'])
            ma_converged = bool(abs(row['ma10'] - row['ma20']) / (row['ma20'] + 1e-9) <= 0.017)
            narrow_range = bool((row['high'] - row['low']) <= row['avg_range20'])
            low_vol = bool(row['volume'] < row['avg_vol10'])
            rsi_ok = bool(row['rsi'] >= row['rsi_smoothed'])
            macd_ok = bool(row['macd'] >= 0 and row['macd_signal'] >= 0)
            above_ma = bool(row['close'] >= row['ma20'] or row['close'] >= row['ma10'])
            above_long_ma = bool(row['close'] >= row['ma50'] and row['close'] >= row['ma100'])
            
            return bool(is_upbar and ma_converged and narrow_range and low_vol and rsi_ok and macd_ok and above_ma and above_long_ma)

        def check_pivot(idx):
            if is_invalid_idx(idx) or idx < 1:
                return False
            row = work_df.iloc[idx]
            prev_row = work_df.iloc[idx-1]
            
            above_mas = bool(row['close'] >= row['ma10'] and row['close'] >= row['ma20'] and row['close'] >= row['ma50'])
            is_upbar = bool(row['close'] > prev_row['close'])
            
            candle_len = row['high'] - row['low']
            candle_ratio = (row['close'] - row['low']) / (candle_len + 1e-9)
            close_high_ratio = bool(candle_ratio >= 0.667)
            
            touches_ma = bool((row['low'] <= row['ma10'] <= row['high']) or (row['low'] <= row['ma20'] <= row['high']))
            high_vol = bool(row['volume'] >= 1.5 * row['avg_vol10'])
            rsi_ok = bool(row['rsi'] >= row['rsi_smoothed'] and row['rsi'] > 50)
            
            has_prior_cuer = False
            for lookback in range(max(0, idx - 5), idx):
                if check_cuer_1_8_first(lookback) or check_cuer_1_8_subsequent(lookback):
                    has_prior_cuer = True
                    break
                    
            return bool(above_mas and is_upbar and close_high_ratio and touches_ma and high_vol and rsi_ok and has_prior_cuer)

        def check_breakout(idx):
            if is_invalid_idx(idx) or idx < 1:
                return False
            row = work_df.iloc[idx]
            prev_row = work_df.iloc[idx-1]
            
            high_vol = bool(row['volume'] >= 1.5 * row['avg_vol10'])
            above_mas = bool(row['close'] >= row['ma10'] and row['close'] >= row['ma20'] and row['close'] >= row['ma50'] and row['close'] >= row['ma100'])
            is_upbar = bool(row['close'] > prev_row['close'])
            
            candle_len = row['high'] - row['low']
            close_pos = (row['close'] - row['low']) / (candle_len + 1e-9) if candle_len > 0 else 1.0
            # Nới lỏng điều kiện closes_at_high: chỉ cần đóng cửa ở 70% thân nến trên (cho phép râu trên <= 30%)
            closes_at_high = bool(close_pos >= 0.70)
            
            large_range = bool(row['price_change_pct'] >= 3.0 or (row['high'] - row['low']) >= 1.2 * row['avg_range20'])
            rsi_ok = bool(row['rsi'] >= row['rsi_smoothed'] and row['rsi'] > 50)
            macd_ok = bool(row['macd'] >= 0 and row['macd_signal'] >= 0)
            
            return bool(high_vol and above_mas and is_upbar and closes_at_high and large_range and rsi_ok and macd_ok)

        def check_volume_surge(idx):
            """
            Cơ chế 'Đột biến thể tích sớm' (Volume Surge Alert):
            - Thanh khoản nổ gấp >= 2.5x TB10 phiên
            - Khối lượng TB10 phiên >= 50,000 cổ phiếu
            - Giá tăng so với phiên trước
            - Đóng cửa ở 70% thân nến trên (cho phép râu trên nhẹ <= 30%)
            - Vị thế giá bám sát hoặc vượt MA10/MA20, RSI > 48
            """
            if is_invalid_idx(idx) or idx < 1:
                return False
            row = work_df.iloc[idx]
            prev_row = work_df.iloc[idx-1]
            
            avg_v10 = row['avg_vol10'] if 'avg_vol10' in row and pd.notna(row['avg_vol10']) else 0.0
            vol = row['volume'] if 'volume' in row and pd.notna(row['volume']) else 0.0
            vol_surge = bool(avg_v10 >= 50000 and vol >= 2.5 * avg_v10)
            
            is_upbar = bool(row['close'] > prev_row['close'])
            candle_len = row['high'] - row['low']
            close_pos = (row['close'] - row['low']) / (candle_len + 1e-9) if candle_len > 0 else 1.0
            closes_top70 = bool(close_pos >= 0.70)
            
            above_mas = bool(row['close'] >= row['ma10'] * 0.98 or row['close'] >= row['ma20'] * 0.98)
            rsi_val = row['rsi'] if 'rsi' in row and pd.notna(row['rsi']) else 50.0
            rsi_ok = bool(rsi_val >= 48.0)
            
            return bool(vol_surge and is_upbar and closes_top70 and above_mas and rsi_ok)

        def count_prior_cuer_points(idx):
            cnt = 0
            for lookback in range(max(0, idx - 60), idx):
                if check_cuer_1_8_first(lookback) or check_cuer_1_8_subsequent(lookback):
                    cnt += 1
            return cnt

        # Determine Recommendation State based on docx rules
        recommendation_status = ""
        recommendation_desc = "Không khuyến nghị: Cổ phiếu chưa xuất hiện điểm mua và điểm tích lũy VSA yếu (<50)."
        
        if check_volume_surge(i):
            recommendation_status = "Múc"
            recommendation_desc = "Điểm Đột Biến Thể Tích Sớm (Volume Surge Alert): Thanh khoản bùng nổ gấp >= 2.5x TB10 (TB10 >= 50.000 cp), đóng nến >= 70% thân nến trên. Dòng tiền lớn kích hoạt chân sóng."
        elif check_breakout(i):
            recommendation_status = "Múc"
            recommendation_desc = "Điểm Nổ (Breakout Bar): Xác nhận cổ phiếu bước vào pha đẩy giá chính thức (Pha E). Tỷ lệ thắng cao nếu nằm trong sóng ngành dẫn dắt."
        elif check_pivot(i):
            recommendation_status = "Múc"
            recommendation_desc = "Điểm Pivot (Điểm nổ sớm): Phiên bứt phá từ nền sau khi đã rũ bỏ và kiệt cung. Bật lên từ hỗ trợ MA10/MA20 với khối lượng lớn."
        elif check_cuer_1_8_subsequent(i):
            prior_cnt = count_prior_cuer_points(i)
            if prior_cnt >= 2:
                recommendation_status = "Múc"
                recommendation_desc = "Điểm BU (Backup / Pullback): Cổ phiếu quay lại kiểm tra vùng đỉnh cũ hoặc hỗ trợ sau bùng nổ, kiệt cung và bật lại."
            else:
                recommendation_status = "Múc"
                recommendation_desc = "Điểm Cược gia tăng (Cược 1/8 lần thứ 2 trở lên): Nền tích lũy chặt chẽ, các đường MA hội tụ, rũ bỏ kiệt cung, MACD thuận lợi."
        elif check_cuer_1_8_first(i):
            recommendation_status = "Múc"
            recommendation_desc = "Điểm Cược 1/8 (Lần 1): Lấy vị thế sớm ngay tại vùng rũ bỏ, kiệt quệ khối lượng trong nền tích lũy. MA10 và MA20 hội tụ sát nhau."
        else:
            is_gayanen = bool(price < latest['ma10'] and price < latest['ma20'] and latest['volume'] >= 1.2 * latest['avg_vol10'] and price < prev_price)
            if is_gayanen or final_score <= 25:
                recommendation_status = "Sút"
                recommendation_desc = "Sút (Thoát hoàn toàn): Nền giá bị đánh gãy với khối lượng lớn hoặc điểm đánh giá giảm mạnh dưới ngưỡng an toàn. Cần thu hồi vốn lập tức."
            elif final_score <= 45 or price < latest['ma50']:
                recommendation_status = "Cảnh báo rủi ro"
                recommendation_desc = "Cảnh báo rủi ro: Cổ phiếu nằm dưới MA50 hoặc điểm tích lũy VSA yếu. Chưa xuất hiện điểm mua an toàn."
            elif final_score >= 50:
                recommendation_status = ""
                recommendation_desc = "Theo dõi: Cổ phiếu chưa đạt điểm mua tối ưu nhưng có điểm VSA tích lũy tốt (>=50)."

        # Collect failed buy reasons for stocks with VSA score >= 50 but no buy signal
        failed_reasons = []
        if final_score >= 50 and recommendation_status == "":
            # Check Cược 1/8 (Lần 1)
            cuer_failed = []
            if not (price > prev_price):
                cuer_failed.append("Giá đóng cửa không tăng")
            ma_diff_pct = (abs(latest['ma10'] - latest['ma20']) / (latest['ma20'] + 1e-9)) * 100
            if ma_diff_pct > 1.7:
                cuer_failed.append(f"Độ lệch MA10/MA20 ({ma_diff_pct:.2f}%) vượt quá 1.7%")
            spread = latest['high'] - latest['low']
            if spread > latest['avg_range20']:
                cuer_failed.append(f"Biên độ giá ({spread:.2f}) chưa đạt chuẩn hẹp (trung bình 20 phiên: {latest['avg_range20']:.2f})")
            if latest['volume'] >= latest['avg_vol10']:
                cuer_failed.append(f"Khối lượng chưa cạn kiệt ({latest['volume']:,.0f} >= trung bình 10 phiên: {latest['avg_vol10']:,.0f})")
            if latest['rsi'] < latest['rsi_smoothed']:
                cuer_failed.append("Chỉ báo RSI nằm dưới đường làm mượt RSI Smoothed")
            if not (price >= latest['ma20'] or price >= latest['ma10']):
                cuer_failed.append("Giá đóng cửa nằm dưới cả hai đường MA10 và MA20")
            if cuer_failed:
                failed_reasons.append("Chưa đạt Điểm Cược 1/8: " + ", ".join(cuer_failed))

            # Check Pivot
            pivot_failed = []
            if not (price >= latest['ma10'] and price >= latest['ma20'] and price >= latest['ma50']):
                pivot_failed.append("Giá chưa nằm trên các đường MA10, MA20, MA50")
            if not (price > prev_price):
                pivot_failed.append("Giá đóng cửa không tăng")
            candle_len = latest['high'] - latest['low']
            candle_ratio = (price - latest['low']) / (candle_len + 1e-9)
            if candle_ratio < 0.667:
                pivot_failed.append(f"Giá đóng cửa không nằm ở 2/3 thân nến trở lên (tỉ lệ: {candle_ratio:.2f})")
            touches_ma = (latest['low'] <= latest['ma10'] <= latest['high']) or (latest['low'] <= latest['ma20'] <= latest['high'])
            if not touches_ma:
                pivot_failed.append("Biên độ giá không chạm qua đường MA10 hoặc MA20")
            if latest['volume'] < 1.5 * latest['avg_vol10']:
                pivot_failed.append(f"Khối lượng ({latest['volume']:,.0f}) chưa đạt 1.5 lần trung bình 10 phiên ({1.5 * latest['avg_vol10']:,.0f})")
            if latest['rsi'] < latest['rsi_smoothed'] or latest['rsi'] <= 50:
                pivot_failed.append("Chỉ báo RSI chưa > 50 hoặc chưa vượt đường làm mượt")
            has_prior_cuer = False
            for lookback in range(max(0, i - 5), i):
                if check_cuer_1_8_first(lookback) or check_cuer_1_8_subsequent(lookback):
                    has_prior_cuer = True
                    break
            if not has_prior_cuer:
                pivot_failed.append("Không xuất hiện điểm Cược 1/8 trong 5 phiên gần nhất")
            if pivot_failed:
                failed_reasons.append("Chưa đạt Điểm Pivot: " + ", ".join(pivot_failed))

            # Check Breakout
            bo_failed = []
            if latest['volume'] < 1.5 * latest['avg_vol10']:
                bo_failed.append(f"Khối lượng ({latest['volume']:,.0f}) chưa đạt 1.5 lần trung bình 10 phiên ({1.5 * latest['avg_vol10']:,.0f})")
            if not (price >= latest['ma10'] and price >= latest['ma20'] and price >= latest['ma50'] and price >= latest['ma100']):
                bo_failed.append("Giá chưa nằm trên các đường MA10, MA20, MA50, MA100")
            if not (price > prev_price):
                bo_failed.append("Giá đóng cửa không tăng")
            candle_len_bo = latest['high'] - latest['low']
            close_pos_bo = (price - latest['low']) / (candle_len_bo + 1e-9) if candle_len_bo > 0 else 1.0
            if close_pos_bo < 0.70:
                bo_failed.append(f"Giá đóng cửa chưa đạt 70% thân nến trên (tỉ lệ: {close_pos_bo*100:.1f}% < 70%)")
            large_range = price_change_pct >= 3.0 or (latest['high'] - latest['low']) >= 1.2 * latest['avg_range20']
            if not large_range:
                bo_failed.append(f"Biên độ giá tăng ({price_change_pct:.1f}%) chưa đạt chuẩn bùng nổ")
            if latest['rsi'] < latest['rsi_smoothed'] or latest['rsi'] <= 50:
                bo_failed.append("Chỉ báo RSI chưa > 50 hoặc chưa vượt đường làm mượt")
            if latest['macd'] < 0 or latest['macd_signal'] < 0:
                bo_failed.append("MACD hoặc Tín hiệu còn nằm dưới mức 0")
            if bo_failed:
                failed_reasons.append("Chưa đạt Điểm Nổ (Breakout): " + ", ".join(bo_failed))

        def safe_float(val):
            return float(val) if pd.notna(val) else None

        avg_vol10_curr = float(latest['avg_vol10']) if 'avg_vol10' in latest and pd.notna(latest['avg_vol10']) else 1.0
        cur_vol = float(latest['volume']) if 'volume' in latest and pd.notna(latest['volume']) else 0.0
        candle_len_curr = float(latest['high'] - latest['low'])
        close_pos_curr = float((price - latest['low']) / (candle_len_curr + 1e-9)) if candle_len_curr > 0 else 1.0
        is_vol_surge_flag = bool(avg_vol10_curr >= 50000 and cur_vol >= 2.5 * avg_vol10_curr and price > prev_price and close_pos_curr >= 0.70)

        res = {
            "symbol": symbol,
            "target_date": target_date_str if target_date_str else str(latest['time']),
            "latest_price": safe_float(latest['close']),
            "price_change": price_change,
            "price_change_pct": safe_float(price_change_pct),
            "score": round(final_score, 1),
            "core_score": round(core_score, 1),
            "aux_score": round(aux_score, 1),
            "rating": rating_text,
            "rating_text": rating_text,
            "rating_color": rating_color,
            "recommendation_status": recommendation_status,
            "recommendation_desc": recommendation_desc,
            "is_volume_surge": is_vol_surge_flag,
            "volume_surge_ratio": round(cur_vol / (avg_vol10_curr + 1e-9), 2),
            "failed_reasons": failed_reasons,
            "core_results": core_results,
            "aux_results": aux_results,
            "core_criteria": core_results,
            "aux_criteria": aux_results,
            "indicators": {
                "price": safe_float(latest['close']),
                "prev_price": safe_float(prev_price),
                "high": safe_float(latest['high']),
                "low": safe_float(latest['low']),
                "range": safe_float(latest['range']),
                "avg_range20": safe_float(latest['avg_range20']),
                "ma10": safe_float(latest['ma10']),
                "ma20": safe_float(latest['ma20']),
                "ma50": safe_float(latest['ma50']),
                "ma100": safe_float(latest['ma100']),
                "ma200": safe_float(latest['ma200']),
                "volume": safe_float(latest['volume']),
                "avg_vol10": safe_float(latest['avg_vol10']),
                "avg_vol20": safe_float(latest['avg_vol20']),
                "volume_ratio": safe_float(latest['volume'] / (latest['avg_vol10'] + 1e-9)),
                "rsi": safe_float(latest['rsi']),
                "rsi_smoothed": safe_float(latest['rsi_smoothed']),
                "macd": safe_float(latest['macd']),
                "macd_signal": safe_float(latest['macd_signal']),
                "ma20_slope": safe_float(latest['ma20_slope']),
                "ma50_slope": safe_float(latest['ma50_slope']),
                "ma_convergence": safe_float(latest['ma_convergence'])
            }
        }
        STOCK_EVAL_CACHE[cache_key] = res
        return res
    except Exception as e:
        return {"error": f"Lỗi hệ thống khi đánh giá {symbol}: {str(e)}"}

# === SECTOR WAVE AND MARGIN STRATEGY LOGIC (WOLFPACK & MARKET RESONANCE) ===

SECTOR_TIERS_CONFIG = {
    "NGAN_HANG": {
        "name": "Ngành Ngân Hàng",
        "tier1": ["VCB", "BID", "CTG", "TCB", "MBB", "VPB", "ACB", "STB", "HDB", "SHB", "TPB", "LPB", "VIB", "MSB", "EIB"],
        "tier2": ["OCB", "SSB", "NAB", "BAB", "NVB", "BVB", "KLB", "VAB", "PGB", "SGB", "ABB", "EVF"]
    },
    "CHUNG_KHOAN": {
        "name": "Ngành Chứng Khoán",
        "tier1": ["SSI", "VND", "VCI", "HCM", "SHS", "MBS", "VIX", "FTS", "BSI", "CTS"],
        "tier2": ["AGR", "BVS", "ORS", "VDS", "TCI", "TVS", "IVS", "WSS", "PSI", "SBS", "APG", "AAS", "BMS", "DSC", "VFS", "VIG", "HBS"]
    },
    "BAT_DONG_SAN": {
        "name": "Ngành Bất Động Sản",
        "tier1": ["VHM", "VIC", "VRE", "NVL", "PDR", "DIG", "DXG", "KDH", "NLG", "KBC", "VPI", "HDC"],
        "tier2": ["CEO", "DXS", "TCH", "BCG", "NTL", "AGG", "IJC", "TDC", "SCR", "LDG", "KHG", "HQC", "QCG", "ITC", "DPG", "HDG", "CII"]
    },
    "THEP": {
        "name": "Ngành Thép & Vật Liệu",
        "tier1": ["HPG", "HSG", "NKG"],
        "tier2": ["VGS", "TLH", "TVN", "SMC"]
    },
    "DAU_KHI": {
        "name": "Ngành Dầu Khí",
        "tier1": ["GAS", "PVD", "PVS", "BSR", "PLX"],
        "tier2": ["PVC", "PVB", "OIL", "PVT"]
    },
    "BAN_LE": {
        "name": "Ngành Bán Lẻ",
        "tier1": ["MWG", "FRT", "PNJ", "DGW", "MSN"],
        "tier2": ["PET", "VGC"]
    },
    "PHAN_BON": {
        "name": "Ngành Phân Bón & Hóa Chất",
        "tier1": ["DGC", "DPM", "DCM", "BFC"],
        "tier2": ["CSV", "LAS", "DDV"]
    },
    "VAN_TAI_BIEN": {
        "name": "Ngành Vận Tải Biển & Cảng Biển",
        "tier1": ["HAH", "GMD", "PVT", "VSC"],
        "tier2": ["VOS", "VIP", "VTO", "TCL", "DXP"]
    }
}

SECTOR_PEERS_MAP = {
    k: cfg["tier1"] + cfg["tier2"] for k, cfg in SECTOR_TIERS_CONFIG.items()
}

SYMBOL_SECTOR_LOOKUP = {
    sym: sector for sector, symbols in SECTOR_PEERS_MAP.items() for sym in symbols
}

# =========================================================================
# HYBRID REALTIME STITCHING ENGINE (KHÂU NỐI NẾN THỜI GIAN THỰC)
# Kết hợp siêu tốc độ đọc nhị phân MetaKit (0.005s) + Bảng giá trực tuyến Live (Vnstock Trading)
# =========================================================================
LIVE_QUOTES_CACHE = {
    "timestamp": 0,
    "data": {}
}
LIVE_CACHE_TTL = 45  # 45 giây cache trong phiên

_LAST_RATE_LIMIT_HIT = 0

def preload_live_price_board(symbols: list) -> dict:
    """
    Kéo bảng giá thời gian thực cho danh sách mã (batch) một lần duy nhất.
    Tốc độ: 80+ mã chỉ mất ~4.4s, 5-10 mã mất ~1.2s.
    Lưu vào bộ nhớ đệm LIVE_QUOTES_CACHE để dùng lại tức thì cho tất cả các luồng quét.
    """
    global LIVE_QUOTES_CACHE, _LAST_RATE_LIMIT_HIT
    if not symbols:
        return LIVE_QUOTES_CACHE["data"]
        
    now_ts = time.time()
    # Nếu vừa bị rate limit trong 60 giây qua, bỏ qua gọi mạng, dùng an toàn dữ liệu nền
    if now_ts - _LAST_RATE_LIMIT_HIT < 60:
        return LIVE_QUOTES_CACHE["data"]
    
    clean_syms = [str(s).upper().strip() for s in symbols if s]
    
    # Kiểm tra nếu cache còn hạn và chứa đủ các mã
    if (now_ts - LIVE_QUOTES_CACHE["timestamp"] < LIVE_CACHE_TTL) and all(s in LIVE_QUOTES_CACHE["data"] for s in clean_syms):
        return LIVE_QUOTES_CACHE["data"]
        
    try:
        from vnstock import Trading
        td = Trading()
        df_board = td.price_board(clean_syms)
        if df_board is not None and not df_board.empty and 'close_price' in df_board.columns:
            for _, row in df_board.iterrows():
                sym = str(row.get('symbol', '')).upper().strip()
                if not sym:
                    continue
                o = float(row.get('open_price', 0.0) or 0.0)
                h = float(row.get('high_price', 0.0) or 0.0)
                l = float(row.get('low_price', 0.0) or 0.0)
                c = float(row.get('close_price', 0.0) or 0.0)
                v = float(row.get('volume_accumulated', 0.0) or 0.0)
                
                # Chuẩn hóa đơn vị về nghìn đồng (như MetaKit / AmiBroker)
                o = o / 1000.0 if o > 1000 else o
                h = h / 1000.0 if h > 1000 else h
                l = l / 1000.0 if l > 1000 else l
                c = c / 1000.0 if c > 1000 else c
                
                # Nếu chưa khớp hoặc bằng 0, fallback tham chiếu
                if c <= 0:
                    ref = float(row.get('reference_price', 0.0) or 0.0)
                    c = ref / 1000.0 if ref > 1000 else ref
                if o <= 0: o = c
                if h <= 0: h = c
                if l <= 0: l = c
                
                LIVE_QUOTES_CACHE["data"][sym] = {
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                    "time": datetime.now().strftime("%Y-%m-%d")
                }
            LIVE_QUOTES_CACHE["timestamp"] = now_ts
    except (Exception, SystemExit, BaseException) as e:
        safe_print(f"Lỗi hoặc giới hạn kết nối bảng giá trực tuyến batch: {e}")
        _LAST_RATE_LIMIT_HIT = time.time()
        
    return LIVE_QUOTES_CACHE["data"]

def get_single_live_quote(symbol: str) -> dict:
    """Lấy thông tin giá khớp & volume realtime của 1 mã (có bộ đệm cache)."""
    global _LAST_RATE_LIMIT_HIT
    sym = symbol.upper().strip()
    now_ts = time.time()
    if (now_ts - LIVE_QUOTES_CACHE["timestamp"] < LIVE_CACHE_TTL) and (sym in LIVE_QUOTES_CACHE["data"]):
        return LIVE_QUOTES_CACHE["data"][sym]
        
    if now_ts - _LAST_RATE_LIMIT_HIT < 60:
        return LIVE_QUOTES_CACHE["data"].get(sym, None)
        
    try:
        preload_live_price_board([sym])
    except (Exception, SystemExit, BaseException):
        _LAST_RATE_LIMIT_HIT = time.time()
        
    return LIVE_QUOTES_CACHE["data"].get(sym, None)

def stitch_live_candle(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Khâu nối nến thời gian thực vào DataFrame lịch sử:
    - Nếu MetaKit chưa có nến hôm nay: APPEND thêm nến hôm nay với giá & vol trực tuyến.
    - Nếu MetaKit đã có nến hôm nay nhưng vol/giá bị cũ: UPDATE ghi đè dòng cuối với số liệu realtime mới nhất.
    """
    if df is None or df.empty:
        return df
        
    now = datetime.now()
    # Chỉ khâu nối trong ngày làm việc Thứ 2 - Thứ 6
    if now.weekday() >= 5:
        return df
        
    today_str = now.strftime("%Y-%m-%d")
    live = get_single_live_quote(symbol)
    if not live or live.get("volume", 0) <= 0:
        return df
        
    df = df.copy()
    last_date = str(df.iloc[-1]['time'])[:10]
    
    if last_date == today_str:
        idx = df.index[-1]
        df.loc[idx, 'open'] = live['open'] if live['open'] > 0 else df.loc[idx, 'open']
        df.loc[idx, 'high'] = max(float(df.loc[idx, 'high']), live['high'])
        df.loc[idx, 'low'] = min(float(df.loc[idx, 'low']), live['low']) if live['low'] > 0 else df.loc[idx, 'low']
        df.loc[idx, 'close'] = live['close'] if live['close'] > 0 else df.loc[idx, 'close']
        if live['volume'] > float(df.loc[idx, 'volume']):
            df.loc[idx, 'volume'] = live['volume']
    elif last_date < today_str:
        new_row = pd.DataFrame([{
            'time': today_str,
            'open': live['open'],
            'high': live['high'],
            'low': live['low'],
            'close': live['close'],
            'volume': live['volume']
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        
    return df

# Cache for prepared stock dataframes
PREPARED_DFS_CACHE = {}

def clear_prepared_dfs_cache(symbol: str = None, clear_live: bool = False):
    """Xóa bộ nhớ cache để ép nạp dữ liệu cập nhật mới nhất từ đĩa/nguồn cấp."""
    global PREPARED_DFS_CACHE, STOCK_EVAL_CACHE, LIVE_QUOTES_CACHE
    if symbol:
        PREPARED_DFS_CACHE.pop(symbol.upper().strip(), None)
        if clear_live:
            LIVE_QUOTES_CACHE["data"].pop(symbol.upper().strip(), None)
    else:
        PREPARED_DFS_CACHE.clear()
        STOCK_EVAL_CACHE.clear()
        if clear_live:
            LIVE_QUOTES_CACHE["data"].clear()
            LIVE_QUOTES_CACHE["timestamp"] = 0

def get_prepared_stock_df(symbol: str, target_date_str: str = None, force_reload: bool = False) -> pd.DataFrame:
    """
    Loads stock data from local/online sources, cleans columns and pre-calculates indicators.
    Cached in memory to allow instant multi-date and multi-stock evaluations.
    """
    symbol = symbol.upper().strip()
    if not force_reload and symbol in PREPARED_DFS_CACHE:
        df = PREPARED_DFS_CACHE[symbol]
        if df is not None and not df.empty:
            return df

    # Load from local Metakit or CSV
    df = load_stock_data_local_only(symbol, target_date_str)
    if (df is None or df.empty) and not os.path.exists(r"C:\MetakitData"):
        df = load_stock_data(symbol, target_date_str)
        
    # Khâu nối nến thời gian thực nếu đang phân tích phiên hôm nay
    if target_date_str is None and df is not None and not df.empty:
        df = stitch_live_candle(df, symbol)
        
    if df is not None and not df.empty and len(df) >= 30:
        # Precompute all indicators once
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['open'] = pd.to_numeric(df['open'], errors='coerce')
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        
        df['ma10'] = df['close'].rolling(window=10).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma50'] = df['close'].rolling(window=50).mean()
        df['ma100'] = df['close'].rolling(window=100).mean()
        df['ma200'] = df['close'].rolling(window=200).mean()
        
        df['avg_vol10'] = df['volume'].rolling(window=10).mean()
        df['avg_vol20'] = df['volume'].rolling(window=20).mean()
        
        df['rsi'] = calculate_rsi(df, period=14)
        df['rsi_smoothed'] = df['rsi'].ewm(span=9, adjust=False).mean()
        
        macd_line, signal_line, _ = calculate_macd(df)
        df['macd'] = macd_line
        df['macd_signal'] = signal_line
        
        df['range'] = df['high'] - df['low']
        df['avg_range20'] = df['range'].rolling(window=20).mean()
        
        df['ma20_slope'] = df['ma20'].diff(3)
        df['ma50_slope'] = df['ma50'].diff(5)
        
        ma_max = df[['ma10', 'ma20', 'ma50']].max(axis=1)
        ma_min = df[['ma10', 'ma20', 'ma50']].min(axis=1)
        df['ma_convergence'] = ((ma_max - ma_min) / (df['ma20'] + 1e-9)) * 100
        
        PREPARED_DFS_CACHE[symbol] = df
        return df

    return df

def load_stock_data_local_only(symbol: str, target_date_str: str = None) -> pd.DataFrame:
    symbol = symbol.upper().strip()
    
    # 1. Try Local CSV File
    base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
    data_dir = os.path.join(base_dir, 'data')
    if not os.path.exists(data_dir) and getattr(sys, 'frozen', False):
        alt_data = os.path.join(getattr(sys, '_MEIPASS', base_dir), 'data')
        if os.path.exists(alt_data):
            data_dir = alt_data
    local_file = os.path.join(data_dir, f"{symbol}.csv")
    if os.path.exists(local_file):
        try:
            df = pd.read_csv(local_file)
            df.columns = [col.lower().strip() for col in df.columns]
            rename_map = {}
            for col in df.columns:
                if col in ['ticker', 'symbol', 'ma']: rename_map[col] = 'symbol'
                elif col in ['date/time', 'datetime', 'date', 'time', 'timestamp']: rename_map[col] = 'time'
                elif col in ['open', 'op']: rename_map[col] = 'open'
                elif col in ['high', 'hi']: rename_map[col] = 'high'
                elif col in ['low', 'lo']: rename_map[col] = 'low'
                elif col in ['close', 'cl']: rename_map[col] = 'close'
                elif col in ['volume', 'vol', 'v']: rename_map[col] = 'volume'
            df = df.rename(columns=rename_map)
            required = ['time', 'open', 'high', 'low', 'close', 'volume']
            if all(req in df.columns for req in required):
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                df = df.dropna(subset=['close', 'volume']).sort_values(by='time').reset_index(drop=True)
                return df
        except Exception:
            pass
            
    # 2. Try Metakit Binary Database (.dat)
    metakit_file = os.path.join(r"C:\MetakitData\AmiBroker\EOD\stock", f"{symbol}.dat")
    if not os.path.exists(metakit_file):
        metakit_file = os.path.join(r"C:\MetakitData\AmiBroker\EOD\index", f"{symbol}.dat")
    if os.path.exists(metakit_file):
        try:
            with open(metakit_file, "rb") as f:
                header = f.read(32)
                if len(header) >= 32:
                    num_recs = struct.unpack("<I", header[:4])[0]
                    dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
                    for _ in range(num_recs):
                        rec = f.read(32)
                        if len(rec) < 32: break
                        date_int, pad, open_p, high_p, low_p, close_p, vol, val = struct.unpack("<IIfffffI", rec)
                        date_str = f"{date_int // 10000}-{(date_int % 10000) // 100 :02d}-{date_int % 100 :02d}"
                        dates.append(date_str)
                        opens.append(open_p)
                        highs.append(high_p)
                        lows.append(low_p)
                        closes.append(close_p)
                        volumes.append(vol)
                    df = pd.DataFrame({"time": dates, "open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes})
                    df = df.dropna(subset=['close', 'volume']).sort_values(by='time').reset_index(drop=True)
                    if not df.empty:
                        return df
        except Exception:
            pass
            
    return pd.DataFrame()

def load_stock_data_short(symbol: str, target_date_str: str = None) -> pd.DataFrame:
    """
    Loads a shorter history for peer stocks to optimize performance.
    """
    df_local = get_prepared_stock_df(symbol, target_date_str)
    if df_local is not None and not df_local.empty:
        return df_local
    if not os.path.exists(r"C:\MetakitData"):
        return load_stock_data(symbol, target_date_str)
    return pd.DataFrame()

def get_sector_peers(symbol_or_sector: str) -> tuple[str, list[str]]:
    """
    Returns the sector name and the list of peer stock symbols.
    Supports either a stock symbol (e.g. "FTS") or a sector key (e.g. "CHUNG_KHOAN").
    """
    symbol_or_sector = symbol_or_sector.upper().strip()
    
    if symbol_or_sector in SECTOR_TIERS_CONFIG:
        cfg = SECTOR_TIERS_CONFIG[symbol_or_sector]
        return cfg["name"], cfg["tier1"] + cfg["tier2"]
        
    sector_key = SYMBOL_SECTOR_LOOKUP.get(symbol_or_sector)
    if not sector_key:
        try:
            from vnstock import Reference
            ref = Reference()
            df_info = ref.company.info(symbol_or_sector)
            if df_info is not None and not df_info.empty:
                sector_name = df_info.get("industry", [None])[0]
                if sector_name:
                    return sector_name, [symbol_or_sector]
        except Exception:
            pass
        return "Khác", [symbol_or_sector]
        
    cfg = SECTOR_TIERS_CONFIG.get(sector_key)
    if cfg:
        return cfg["name"], cfg["tier1"] + cfg["tier2"]
    return "Khác", [symbol_or_sector]

def evaluate_single_peer(symbol: str, target_date_str: str = None):
    try:
        df = load_stock_data_short(symbol, target_date_str)
        if df.empty or len(df) < 30:
            return None
        res = evaluate_stock_from_df(df, symbol, target_date_str)
        if "error" not in res:
            return symbol, res
    except Exception:
        pass
    return None

import time
PEER_EVALUATION_CACHE = {}
CACHE_TTL_SECONDS = 600

def evaluate_single_peer_cached(symbol: str, target_date_str: str = None):
    key = (symbol, target_date_str)
    now = time.time()
    if key in PEER_EVALUATION_CACHE:
        cache_ts, res = PEER_EVALUATION_CACHE[key]
        if now - cache_ts < CACHE_TTL_SECONDS:
            return res
    res = evaluate_single_peer(symbol, target_date_str)
    if res is not None:
        PEER_EVALUATION_CACHE[key] = (now, res)
    return res

def evaluate_sector_wave(symbol_or_sector: str, target_date_str: str = None) -> dict:
    """
    Evaluates Sector Wave based on Wolfpack & Market Resonance Theory:
    - Scout Wolf (Sói Dò Đường) & Echo Buys within 5 trading sessions (T0 -> T+5).
    - Tier 1 vs Tier 2 breadth & moving average consensus (Tier 1 >= 55% above MA50).
    - VNINDEX Market Resonance (VNINDEX >= MA50 & Volume >= 1.15x MA20).
    - Clear State & Margin Strategy Hand-off (Mốc A, Mốc B, Sói Dò Đường, Sói Đơn Độc, Phân Hóa, Tích Lũy).
    """
    symbol_or_sector = symbol_or_sector.upper().strip()
    
    # 1. Resolve Sector Key
    sector_key = None
    if symbol_or_sector in SECTOR_TIERS_CONFIG:
        sector_key = symbol_or_sector
    elif symbol_or_sector in SYMBOL_SECTOR_LOOKUP:
        sector_key = SYMBOL_SECTOR_LOOKUP[symbol_or_sector]
    else:
        for k in SECTOR_TIERS_CONFIG:
            if k in symbol_or_sector or symbol_or_sector in k:
                sector_key = k
                break

    if not sector_key or sector_key not in SECTOR_TIERS_CONFIG:
        return {
            "sector_name": "Khác",
            "sector_key": "KHAC",
            "state": "CHUA_CO_SONG",
            "status": "🔴 Chưa có Sóng Ngành",
            "score": 0.0,
            "badge_color": "danger",
            "reason": f"Mã hoặc nhóm ngành {symbol_or_sector} chưa thuộc danh mục phân tích sóng ngành.",
            "margin_recommendation": "⚠️ Tuyệt đối KHÔNG sử dụng Margin."
        }

    cfg = SECTOR_TIERS_CONFIG[sector_key]
    sector_name = cfg["name"]
    tier1_symbols = cfg["tier1"]
    tier2_symbols = cfg["tier2"]
    all_symbols = tier1_symbols + tier2_symbols

    # 2. Load all stock dataframes
    stock_dfs = {}
    for s in all_symbols:
        df_s = get_prepared_stock_df(s, target_date_str)
        if df_s is not None and not df_s.empty:
            stock_dfs[s] = df_s

    if not stock_dfs:
        return {
            "sector_name": sector_name,
            "sector_key": sector_key,
            "state": "CHUA_CO_SONG",
            "status": "🔴 Chưa có Sóng Ngành",
            "score": 0.0,
            "badge_color": "danger",
            "reason": f"Không tìm thấy dữ liệu cho các cổ phiếu thuộc {sector_name}.",
            "margin_recommendation": "⚠️ Tuyệt đối KHÔNG sử dụng Margin."
        }

    # 3. Determine target date and date sequence
    sample_df = next(iter(stock_dfs.values()))
    if target_date_str:
        avail_dates = sample_df[sample_df['time'] <= target_date_str]['time'].tolist()
        eval_date = avail_dates[-1] if avail_dates else sample_df['time'].iloc[-1]
    else:
        eval_date = sample_df['time'].iloc[-1]

    all_dates = sample_df['time'].tolist()
    if eval_date in all_dates:
        curr_idx = all_dates.index(eval_date)
    else:
        curr_idx = len(all_dates) - 1

    # 4. Evaluate all stocks on eval_date
    t1_results = {}
    t2_results = {}
    today_buys = []
    today_tier1_buys = []
    t1_above_ma50_count = 0
    t1_sell_count = 0
    max_score = 0.0
    leader_symbol = None

    for s in tier1_symbols:
        if s in stock_dfs:
            res = evaluate_stock_from_df(stock_dfs[s], s, eval_date)
            t1_results[s] = res
            sc = res.get("score", 0.0)
            if sc > max_score:
                max_score = sc
                leader_symbol = s
            ind = res.get("indicators", {})
            p = ind.get("price", 0.0)
            ma50 = ind.get("ma50", 0.0)
            if p and ma50 and p >= ma50:
                t1_above_ma50_count += 1
            
            is_buy = res.get("recommendation_status") == "Múc" or sc >= 75.0
            is_sell = res.get("recommendation_status") == "Sút" or (p and ma50 and p < ma50 and res.get("price_change_pct", 0) < -2.0)
            
            if is_buy:
                today_buys.append(s)
                today_tier1_buys.append(s)
            if is_sell:
                t1_sell_count += 1

    for s in tier2_symbols:
        if s in stock_dfs:
            res = evaluate_stock_from_df(stock_dfs[s], s, eval_date)
            t2_results[s] = res
            sc = res.get("score", 0.0)
            if sc > max_score and leader_symbol is None:
                max_score = sc
                leader_symbol = s
            if res.get("recommendation_status") == "Múc" or sc >= 75.0:
                today_buys.append(s)

    total_t1 = len(t1_results) if t1_results else 1
    t1_above_ma50_pct = (t1_above_ma50_count / total_t1) * 100
    t1_sell_pct = (t1_sell_count / total_t1) * 100

    # 5. Scan History for Scout Wolf (T0) and Echo Buys (T0 -> T+5)
    # 5.1 First look for an active Scout in the current window (0 <= offset <= 5)
    scout_wolf = None
    scout_date = None
    scout_days_ago = None
    echo_buys_set = set()

    for offset in range(min(5, curr_idx), -1, -1):
        d_idx = curr_idx - offset
        if d_idx < 0: continue
        past_date = all_dates[d_idx]
        
        past_t1_buys = []
        for s in tier1_symbols:
            if s in stock_dfs:
                p_res = evaluate_stock_from_df(stock_dfs[s], s, past_date)
                if p_res.get("recommendation_status") == "Múc" or p_res.get("score", 0.0) >= 75.0:
                    past_t1_buys.append(s)
                    
        if scout_wolf is None and past_t1_buys:
            scout_wolf = past_t1_buys[0]
            scout_date = past_date
            scout_days_ago = offset
            
        if scout_wolf is not None:
            for s in past_t1_buys:
                if s != scout_wolf:
                    echo_buys_set.add(s)

    # 5.2 If no active scout in last 5 sessions, check for an expired scout (6-10 sessions ago)
    expired_scout = None
    expired_date = None
    if scout_wolf is None:
        for offset in range(min(10, curr_idx), 5, -1):
            d_idx = curr_idx - offset
            if d_idx < 0: continue
            past_date = all_dates[d_idx]
            for s in tier1_symbols:
                if s in stock_dfs:
                    p_res = evaluate_stock_from_df(stock_dfs[s], s, past_date)
                    if p_res.get("recommendation_status") == "Múc" or p_res.get("score", 0.0) >= 75.0:
                        expired_scout = s
                        expired_date = past_date
                        break
            if expired_scout:
                break

    echo_buys = list(echo_buys_set)

    # 6. Evaluate VN-INDEX Resonance
    vni_safe = True
    vni_vol_expanding = False
    vni_desc = "VNINDEX ổn định."
    try:
        df_vni = get_prepared_stock_df("VNINDEX", eval_date)
        if df_vni is not None and not df_vni.empty:
            df_vni_sub = df_vni[df_vni['time'] <= eval_date]
            if len(df_vni_sub) >= 20:
                vni_row = df_vni_sub.iloc[-1]
                vni_close = float(vni_row['close'])
                vni_ma50 = float(vni_row['ma50']) if 'ma50' in vni_row and not pd.isna(vni_row['ma50']) else vni_close
                vni_vol = float(vni_row['volume'])
                vni_ma20_vol = float(vni_row['avg_vol20']) if 'avg_vol20' in vni_row and not pd.isna(vni_row['avg_vol20']) else vni_vol
                
                vni_safe = vni_close >= vni_ma50
                vni_vol_expanding = vni_vol >= (1.15 * vni_ma20_vol)
                
                if vni_vol_expanding:
                    vni_desc = f"Thanh khoản VNINDEX nở rộ (Vol >= 1.15x MA20) - Dòng tiền lan tỏa mạnh mẽ."
                elif vni_safe:
                    vni_desc = f"VNINDEX ({vni_close:,.1f}) trên MA50 ({vni_ma50:,.1f})."
                else:
                    vni_desc = f"VNINDEX ({vni_close:,.1f}) dưới MA50 ({vni_ma50:,.1f})."
    except Exception as e:
        safe_print("VNI eval error:", e)

    # 7. State & Wolfpack Logic Decision
    state = "TICH_LUY"
    status = "⚪ Tích Lũy Kiệt Cung"
    score = 45.0
    badge_color = "warning"
    margin_rec = "Thăm dò 12.5% tiền mặt tại ST/LPS. Tuyệt đối KHÔNG dùng Margin."
    alpha_leader = None

    has_active_scout = scout_wolf is not None and scout_days_ago is not None and scout_days_ago <= 5
    has_echo_pack = len(echo_buys) >= 2
    is_t1_strong = t1_above_ma50_pct >= 55.0 or (t1_above_ma50_pct >= 50.0 and len(today_buys) >= 2)
    is_selling_off = t1_sell_pct >= 35.0 or (t1_above_ma50_pct < 40.0 and not (has_active_scout and len(today_buys) >= 1))

    if has_active_scout and has_echo_pack and is_t1_strong:
        alpha_leader = scout_wolf
        if vni_safe and vni_vol_expanding:
            state = "MOC_B_NGANH_DAN"
            status = f"🚀 MỐC B: SÓNG NGÀNH DẪN DẮT (Lan Tỏa Dòng Tiền & Leader {alpha_leader})"
            score = 95.0
            badge_color = "success"
            margin_rec = "KÍCH HOẠT FULL MARGIN (100% Tiền + Tối đa Margin). Sóng ngành dẫn dắt toàn thị trường."
        else:
            state = "MOC_A_DONG_SOI"
            status = f"🟢 MỐC A: SÓNG NGÀNH (Đàn Sói & Leader {alpha_leader})"
            score = 85.0
            badge_color = "success"
            margin_rec = f"Giải ngân 50-75% vốn vào Leader {alpha_leader} & Đàn sói. Chưa mở full margin."
    elif has_active_scout:
        state = "SOI_DO_DUONG"
        status = f"🟡 Sói Dò Đường ({scout_wolf}) - Chờ Đàn Tiếp Ứng"
        score = 65.0
        badge_color = "warning"
        margin_rec = f"Mở Mua 1 (25% tiền mặt) vào {scout_wolf}. Chờ đàn tiếp ứng, CHƯA DÙNG Margin."
    elif is_selling_off:
        state = "PHAN_HOA"
        status = "⚠️ Phân Hóa / Rủi Ro Suy Yếu"
        score = 25.0
        badge_color = "danger"
        margin_rec = "Hạ toàn bộ margin, chốt lời từng phần, thu hẹp quy mô vốn quản trị rủi ro."
    elif expired_scout is not None and t1_above_ma50_pct < 45.0:
        state = "SOI_DON_DOC"
        status = f"🔴 Sói Đơn Độc ({expired_scout}) - Không Tạo Sóng Ngành"
        score = 35.0
        badge_color = "danger"
        margin_rec = "⚠️ Tuyệt đối KHÔNG dùng Margin. Cổ phiếu đơn lẻ, khó hình thành sóng ngành."
    else:
        state = "TICH_LUY"
        status = "⚪ Tích Lũy Kiệt Cung"
        score = 45.0
        badge_color = "warning"
        margin_rec = "Thăm dò 12.5% tiền mặt tại ST/LPS. Tuyệt đối KHÔNG dùng Margin."

    reasons = [f"{sector_name}: {status}"]
    if scout_wolf:
        leader_label = "Sói đầu đàn" if alpha_leader else "Sói dò đường"
        reasons.append(f"{leader_label} {scout_wolf} (phát súng hiệu {scout_date})")
    if echo_buys:
        reasons.append(f"Mã tiếp ứng: {', '.join(echo_buys[:4])}")
    reasons.append(f"Tier 1 trên MA50 đạt {t1_above_ma50_pct:.1f}% ({t1_above_ma50_count}/{total_t1} mã)")
    if vni_desc:
        reasons.append(vni_desc)

    reason_str = ". ".join(reasons) + "."

    return {
        "date": eval_date,
        "sector_name": sector_name,
        "sector_key": sector_key,
        "state": state,
        "status": status,
        "score": score,
        "badge_color": badge_color,
        "scout_wolf": scout_wolf,
        "scout_date": scout_date,
        "alpha_leader": alpha_leader,
        "leader": alpha_leader or leader_symbol or (scout_wolf if scout_wolf else "Chưa có Leader"),
        "leader_score": round(max_score, 1),
        "echo_buys": echo_buys,
        "today_buys": today_buys,
        "buy_signals_count": len(today_buys),
        "sell_signals_count": t1_sell_count,
        "tier1_above_ma50_pct": round(t1_above_ma50_pct, 1),
        "tier1_sell_pct": round(t1_sell_pct, 1),
        "vni_vol_expanding": vni_vol_expanding,
        "vni_safe": vni_safe,
        "margin_recommendation": margin_rec,
        "reason": reason_str
    }

def evaluate_stock(symbol: str, target_date_str: str = None) -> dict:
    """
    Main evaluation entry point that combines VSA stock rating and Sector Wave analysis.
    """
    try:
        df = get_prepared_stock_df(symbol, target_date_str=target_date_str)
        if df is None or df.empty or len(df) < 30:
            return {"error": f"Không đủ dữ liệu giao dịch cho cổ phiếu {symbol}."}
            
        res = evaluate_stock_from_df(df, symbol, target_date_str)
        return res
    except Exception as e:
        return {"error": f"Lỗi hệ thống khi đánh giá {symbol}: {str(e)}"}
