import os
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import glob
import struct
import time
import json
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")
os.makedirs(DATA_MART_DIR, exist_ok=True)

METAKIT_STOCK_DIR = r"C:\MetakitData\AmiBroker\EOD\stock"
METAKIT_INDEX_DIR = r"C:\MetakitData\AmiBroker\EOD\index"

# 1. Load Sector Lookup
try:
    from evaluator import SYMBOL_SECTOR_LOOKUP
except ImportError:
    SYMBOL_SECTOR_LOOKUP = {}

# 2. Load VN-Index and Precompute Market Indicators
def load_vni_regime():
    vni_file = os.path.join(METAKIT_INDEX_DIR, "VNINDEX.dat")
    if not os.path.exists(vni_file):
        return pd.DataFrame()
    with open(vni_file, "rb") as f:
        hdr = f.read(32)
        if len(hdr) < 32: return pd.DataFrame()
        num = struct.unpack("<I", hdr[:4])[0]
        dates, closes, volumes = [], [], []
        for _ in range(num):
            rec = f.read(32)
            if len(rec) < 32: break
            d_int, pad, op, hi, lo, cl, vol, val = struct.unpack("<IIfffffI", rec)
            if d_int < 20050101: continue
            date_str = f"{d_int // 10000}-{(d_int % 10000) // 100 :02d}-{d_int % 100 :02d}"
            dates.append(date_str)
            closes.append(float(cl))
            volumes.append(float(vol))
    df = pd.DataFrame({"time": dates, "vni_close": closes, "vni_vol": volumes})
    df = df.drop_duplicates(subset=["time"]).sort_values(by="time").reset_index(drop=True)
    df["vni_ma20"] = df["vni_close"].rolling(20, min_periods=10).mean()
    df["vni_ma50"] = df["vni_close"].rolling(50, min_periods=20).mean()
    df["vni_ret_60"] = df["vni_close"].pct_change(60) * 100.0
    df["vni_ret_120"] = df["vni_close"].pct_change(120) * 100.0
    df["vni_chg_pct"] = df["vni_close"].pct_change() * 100.0
    
    # 20-day drawdown of VN-Index
    roll_max_20 = df["vni_close"].rolling(20, min_periods=10).max()
    df["vni_dd_20"] = (df["vni_close"] - roll_max_20) / roll_max_20 * 100.0
    
    # Market Regime: 1 = Uptrend, 0 = Sideway, -1 = Downtrend
    conditions = [
        (df["vni_close"] > df["vni_ma20"]) & (df["vni_close"] > df["vni_ma50"]),
        (df["vni_close"] < df["vni_ma20"]) & (df["vni_close"] < df["vni_ma50"])
    ]
    choices = [1, -1]
    df["vni_regime"] = np.select(conditions, choices, default=0)
    return df.set_index("time")

# 3. Load Sector Wave Matrix
def load_sector_wave():
    sec_path = os.path.join(DATA_MART_DIR, "sector_wave_matrix_2007_2026.parquet")
    if os.path.exists(sec_path):
        sec_df = pd.read_parquet(sec_path)
        # Create a lookup multi-index or dict: (time, sector) -> sector_wave_score
        lookup = {}
        for _, row in sec_df.iterrows():
            lookup[(row["time"], row["sector"])] = float(row.get("sector_wave_score", 50.0))
        return lookup
    return {}

# 4. Parse Stock Dat file
def parse_stock_dat(file_path):
    symbol = os.path.basename(file_path).replace(".dat", "").upper()
    try:
        with open(file_path, "rb") as f:
            hdr = f.read(32)
            if len(hdr) < 32: return None
            num = struct.unpack("<I", hdr[:4])[0]
            if num < 120: return None
            dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
            for _ in range(num):
                rec = f.read(32)
                if len(rec) < 32: break
                d_int, pad, op, hi, lo, cl, vol, val = struct.unpack("<IIfffffI", rec)
                if d_int < 20050101: continue
                if op <= 0 or hi <= 0 or lo <= 0 or cl <= 0: continue
                date_str = f"{d_int // 10000}-{(d_int % 10000) // 100 :02d}-{d_int % 100 :02d}"
                dates.append(date_str)
                opens.append(float(op))
                highs.append(float(hi))
                lows.append(float(lo))
                closes.append(float(cl))
                volumes.append(float(vol))
        if len(dates) < 100: return None
        df = pd.DataFrame({
            "time": dates,
            "symbol": symbol,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes
        })
        df = df.drop_duplicates(subset=["time"]).sort_values(by="time").reset_index(drop=True)
        return df
    except Exception:
        return None

def extract_features():
    t0 = time.time()
    print("======================================================================")
    print("⚡ BẮT ĐẦU TRÍCH XUẤT 30 ĐẶC TRƯNG ĐỊNH LƯỢNG SIÊU CỔ PHIẾU (T0 & T1) ⚡")
    print("======================================================================")
    
    labels_parquet = os.path.join(DATA_MART_DIR, "super_stock_training_labels.parquet")
    if not os.path.exists(labels_parquet):
        print(f"Lỗi: Không tìm thấy file {labels_parquet}!")
        return
        
    df_labels = pd.read_parquet(labels_parquet)
    print(f"Tổng số điểm ứng viên cần trích xuất đặc trưng: {len(df_labels):,}")
    
    # Preload Market Context
    print("1. Đang nạp bối cảnh thị trường VN-Index và Sóng Ngành...")
    vni_map = load_vni_regime()
    sec_wave_lookup = load_sector_wave()
    print(f"   VN-Index history: {len(vni_map):,} phiên. Sóng ngành: {len(sec_wave_lookup):,} điểm quan sát.")
    
    # Group candidates by symbol
    grouped_cands = df_labels.groupby("symbol")
    symbols = list(grouped_cands.groups.keys())
    print(f"2. Bắt đầu tính toán cho {len(symbols):,} mã cổ phiếu...")
    
    feature_rows = []
    processed_count = 0
    
    for sym in symbols:
        cands_sub = grouped_cands.get_group(sym)
        cands_times = set(cands_sub["time"].values)
        
        fpath = os.path.join(METAKIT_STOCK_DIR, f"{sym}.dat")
        df_stock = parse_stock_dat(fpath)
        if df_stock is None or df_stock.empty:
            continue
            
        n = len(df_stock)
        if n < 60:
            continue
            
        closes = df_stock["close"].values
        opens = df_stock["open"].values
        highs = df_stock["high"].values
        lows = df_stock["low"].values
        vols = df_stock["volume"].values
        times = df_stock["time"].values
        
        # Sector
        sector_name = SYMBOL_SECTOR_LOOKUP.get(sym, "OTHER")
        
        # Precompute series for this stock
        s_close = df_stock["close"]
        s_open = df_stock["open"]
        s_vol = df_stock["volume"]
        s_high = df_stock["high"]
        s_low = df_stock["low"]
        
        # Moving averages
        ma10 = s_close.rolling(10, min_periods=5).mean().values
        ma20 = s_close.rolling(20, min_periods=10).mean().values
        ma50 = s_close.rolling(50, min_periods=20).mean().values
        ma200 = s_close.rolling(200, min_periods=50).mean().values
        avg_vol20 = s_vol.rolling(20, min_periods=10).mean().values
        avg_vol50 = s_vol.rolling(50, min_periods=20).mean().values
        
        # True Range and ATR
        prev_close = s_close.shift(1).fillna(s_close).values
        tr1 = highs - lows
        tr2 = np.abs(highs - prev_close)
        tr3 = np.abs(lows - prev_close)
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        s_tr = pd.Series(tr)
        atr5 = s_tr.rolling(5, min_periods=3).mean().values
        atr20 = s_tr.rolling(20, min_periods=10).mean().values
        
        # Rolling 52-week High (approx 250 bars)
        roll_high_250 = s_high.rolling(250, min_periods=50).max().values
        
        # Returns
        ret_60 = s_close.pct_change(60).values * 100.0
        ret_120 = s_close.pct_change(120).values * 100.0
        
        # On-Balance Volume (OBV)
        direction = np.sign(s_close.diff().fillna(0).values)
        obv = np.cumsum(direction * vols)
        s_obv = pd.Series(obv)
        obv_ma10 = s_obv.rolling(10, min_periods=5).mean().values
        
        # Time to index lookup
        time_to_idx = {times[i]: i for i in range(n)}
        
        # Iterate candidates for this stock
        for _, c_row in cands_sub.iterrows():
            c_time = c_row["time"]
            if c_time not in time_to_idx:
                continue
            i = time_to_idx[c_time]
            if i < 30: # Need enough lookback
                continue
                
            c0 = closes[i]
            o0 = opens[i]
            h0 = highs[i]
            l0 = lows[i]
            v0 = vols[i]
            av20 = avg_vol20[i] if avg_vol20[i] > 0 else 1.0
            av50 = avg_vol50[i] if avg_vol50[i] > 0 else 1.0
            
            # 1. Relative Strength vs VN-Index
            vni_data = vni_map.loc[c_time] if c_time in vni_map.index else None
            if vni_data is not None:
                vni_r60 = vni_data["vni_ret_60"] if not np.isnan(vni_data["vni_ret_60"]) else 0.0
                vni_r120 = vni_data["vni_ret_120"] if not np.isnan(vni_data["vni_ret_120"]) else 0.0
                vni_regime = int(vni_data["vni_regime"])
                vni_chg = float(vni_data["vni_chg_pct"]) if not np.isnan(vni_data["vni_chg_pct"]) else 0.0
                vni_close_p = float(vni_data["vni_close"])
                vni_m20 = float(vni_data["vni_ma20"]) if not np.isnan(vni_data["vni_ma20"]) else vni_close_p
                vni_m50 = float(vni_data["vni_ma50"]) if not np.isnan(vni_data["vni_ma50"]) else vni_close_p
                vni_vs_m20 = (vni_close_p / vni_m20 - 1.0) * 100.0 if vni_m20 > 0 else 0.0
                vni_vs_m50 = (vni_close_p / vni_m50 - 1.0) * 100.0 if vni_m50 > 0 else 0.0
                vni_dd20 = float(vni_data["vni_dd_20"]) if not np.isnan(vni_data["vni_dd_20"]) else 0.0
            else:
                vni_r60, vni_r120, vni_regime, vni_chg = 0.0, 0.0, 0, 0.0
                vni_vs_m20, vni_vs_m50, vni_dd20 = 0.0, 0.0, 0.0
                
            rs_rating_60 = (ret_60[i] - vni_r60) if not np.isnan(ret_60[i]) else 0.0
            rs_rating_120 = (ret_120[i] - vni_r120) if not np.isnan(ret_120[i]) else 0.0
            
            # 2. VDU (Volume Dry-Up) in Base (prior 20 days)
            prior_vols = vols[max(0, i - 20) : i]
            prior_av20 = avg_vol20[max(0, i - 20) : i]
            vdu_count = np.sum(prior_vols < (prior_av20 * 0.85)) if len(prior_vols) > 0 else 0
            vdu_ratio_20 = (vdu_count / len(prior_vols) * 100.0) if len(prior_vols) > 0 else 0.0
            
            # Vol Up / Vol Down Ratio in prior 20 days
            prior_closes = closes[max(0, i - 20) : i]
            prior_opens = opens[max(0, i - 20) : i]
            up_mask = prior_closes >= prior_opens
            vol_up = np.sum(prior_vols[up_mask]) if len(prior_vols) > 0 else 1.0
            vol_down = np.sum(prior_vols[~up_mask]) if len(prior_vols) > 0 else 1.0
            vol_up_down_ratio = float(vol_up / (vol_down + 1e-5))
            
            # 3. Institutional Deposits (Smart Money) in prior 20 days
            # Count bars with vol >= 1.4 * avg_vol20 and close > open
            deposit_mask = (prior_vols >= (prior_av20 * 1.4)) & up_mask
            deposit_count_20 = int(np.sum(deposit_mask)) if len(prior_vols) > 0 else 0
            
            # OBV Trend: OBV vs OBV_MA10
            obv_slope = float((obv[i] - obv_ma10[i]) / (abs(obv_ma10[i]) + 1e-5) * 100.0) if not np.isnan(obv_ma10[i]) else 0.0
            
            # 4. Base Depth & VCP Contraction
            prior_highs = highs[max(0, i - 25) : i]
            prior_lows = lows[max(0, i - 25) : i]
            base_max = np.max(prior_highs) if len(prior_highs) > 0 else c0
            base_min = np.min(prior_lows) if len(prior_lows) > 0 else c0
            base_depth_pct = (base_max - base_min) / (base_max + 1e-5) * 100.0
            vcp_ratio = float(atr5[i] / (atr20[i] + 1e-5)) if not np.isnan(atr5[i]) and not np.isnan(atr20[i]) else 1.0
            
            # Distance to 52w high
            h52w = roll_high_250[i] if not np.isnan(roll_high_250[i]) and roll_high_250[i] > 0 else c0
            dist_to_52w_high = (c0 - h52w) / h52w * 100.0
            is_near_52w_high = 1 if dist_to_52w_high >= -5.0 else 0
            
            # 5. MA Alignment & Parabolic Curve
            m10 = ma10[i] if not np.isnan(ma10[i]) else c0
            m20 = ma20[i] if not np.isnan(ma20[i]) else c0
            m50 = ma50[i] if not np.isnan(ma50[i]) else c0
            m200 = ma200[i] if not np.isnan(ma200[i]) else c0
            
            close_vs_ma10 = (c0 / m10 - 1.0) * 100.0 if m10 > 0 else 0.0
            close_vs_ma20 = (c0 / m20 - 1.0) * 100.0 if m20 > 0 else 0.0
            close_vs_ma50 = (c0 / m50 - 1.0) * 100.0 if m50 > 0 else 0.0
            close_vs_ma200 = (c0 / m200 - 1.0) * 100.0 if m200 > 0 else 0.0
            ma_alignment_score = 1 if (m10 > m20 and m20 > m50 and c0 > m200) else 0
            
            # 6. T0 Surge Candle Characteristics
            t0_vol_ratio_ma20 = float(v0 / av20)
            t0_vol_ratio_ma50 = float(v0 / av50)
            candle_range = h0 - l0
            t0_close_pos = float((c0 - l0) / (candle_range + 1e-5))
            t0_upper_wick_ratio = float((h0 - max(o0, c0)) / (candle_range + 1e-5))
            t0_spread_ratio = float(candle_range / (atr20[i] + 1e-5)) if not np.isnan(atr20[i]) else 1.0
            
            # 7. Tennis Ball Score
            # Stock 20-day drawdown vs VN-Index 20-day drawdown
            stock_dd20 = (c0 - base_max) / (base_max + 1e-5) * 100.0
            # If market fell -10% and stock only fell -2%, tennis_ball = (-10) - (-2) = -8... Wait:
            # More resilient means stock drawdown is shallower than VNI drawdown:
            tennis_ball_score = float(stock_dd20 - vni_dd20) # positive if stock held up better than VNI
            
            # 8. Sector Wave Score
            sec_score = sec_wave_lookup.get((c_time, sector_name), 50.0)
            
            # Append Row
            feature_rows.append({
                "time": c_time,
                "symbol": sym,
                "sector": sector_name,
                "target_label": int(c_row["target_label"]),
                "mfe_pct": float(c_row["mfe_pct"]),
                "mae_pct": float(c_row["mae_pct"]),
                "days_to_peak": int(c_row["days_to_peak"]),
                # Features available at T0:
                "rs_rating_60": float(rs_rating_60),
                "rs_rating_120": float(rs_rating_120),
                "vdu_ratio_20": float(vdu_ratio_20),
                "vol_up_down_ratio": float(vol_up_down_ratio),
                "deposit_count_20": int(deposit_count_20),
                "obv_slope": float(obv_slope),
                "base_depth_pct": float(base_depth_pct),
                "vcp_ratio": float(vcp_ratio),
                "dist_to_52w_high": float(dist_to_52w_high),
                "is_near_52w_high": int(is_near_52w_high),
                "close_vs_ma10": float(close_vs_ma10),
                "close_vs_ma20": float(close_vs_ma20),
                "close_vs_ma50": float(close_vs_ma50),
                "close_vs_ma200": float(close_vs_ma200),
                "ma_alignment_score": int(ma_alignment_score),
                "t0_chg_pct": float(c_row["chg_pct"]),
                "t0_vol_ratio_ma20": float(t0_vol_ratio_ma20),
                "t0_vol_ratio_ma50": float(t0_vol_ratio_ma50),
                "t0_close_pos": float(t0_close_pos),
                "t0_upper_wick_ratio": float(t0_upper_wick_ratio),
                "t0_spread_ratio": float(t0_spread_ratio),
                "tennis_ball_score": float(tennis_ball_score),
                "sector_wave_score": float(sec_score),
                "vni_regime": int(vni_regime),
                "vni_chg_pct": float(vni_chg),
                "vni_vs_ma20": float(vni_vs_m20),
                "vni_vs_ma50": float(vni_vs_m50),
                # Day 2 Confirmation Features:
                "day2_ret_pct": float(c_row["day2_ret_pct"]),
                "day2_held_50pct": int(c_row["day2_held_50pct"]),
                "day2_vol_ratio": float(c_row["day2_vol_ratio"])
            })
            
        processed_count += 1
        if processed_count % 200 == 0:
            print(f"   Đã trích xuất đặc trưng cho {processed_count}/{len(symbols)} cổ phiếu...")
            
    df_feat = pd.DataFrame(feature_rows)
    print(f"\n=> Hoàn tất trích xuất đặc trưng trong {time.time() - t0:.2f}s!")
    print(f"=> Tổng số mẫu đặc trưng thu được: {len(df_feat):,}")
    print(f"=> Số cột đặc trưng: {len(df_feat.columns)}")
    
    # Save output
    out_parquet = os.path.join(DATA_MART_DIR, "super_stock_features_dataset.parquet")
    df_feat.to_parquet(out_parquet, index=False)
    print(f"=> Đã lưu bộ dữ liệu đặc trưng tại: {out_parquet}")
    return df_feat

if __name__ == "__main__":
    extract_features()
