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
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")
os.makedirs(DATA_MART_DIR, exist_ok=True)

METAKIT_STOCK_DIR = r"C:\MetakitData\AmiBroker\EOD\stock"
METAKIT_INDEX_DIR = r"C:\MetakitData\AmiBroker\EOD\index"

# 1. Load VN-Index for Market Context and RS
def load_vni():
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
            if d_int < 20060101: continue
            date_str = f"{d_int // 10000}-{(d_int % 10000) // 100 :02d}-{d_int % 100 :02d}"
            dates.append(date_str)
            closes.append(float(cl))
            volumes.append(float(vol))
    df = pd.DataFrame({"time": dates, "vni_close": closes, "vni_vol": volumes})
    df = df.drop_duplicates(subset=["time"]).sort_values(by="time").reset_index(drop=True)
    df["vni_ma20"] = df["vni_close"].rolling(20, min_periods=10).mean()
    df["vni_ma50"] = df["vni_close"].rolling(50, min_periods=20).mean()
    df["vni_ret_60"] = df["vni_close"].pct_change(60)
    df["vni_ret_120"] = df["vni_close"].pct_change(120)
    df["vni_chg_pct"] = df["vni_close"].pct_change() * 100.0
    return df

# 2. Parse individual stock dat file
def parse_stock_dat(file_path):
    symbol = os.path.basename(file_path).replace(".dat", "").upper()
    try:
        with open(file_path, "rb") as f:
            hdr = f.read(32)
            if len(hdr) < 32: return None
            num = struct.unpack("<I", hdr[:4])[0]
            if num < 200: return None # skip if not enough history
            
            dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
            for _ in range(num):
                rec = f.read(32)
                if len(rec) < 32: break
                d_int, pad, op, hi, lo, cl, vol, val = struct.unpack("<IIfffffI", rec)
                if d_int < 20060101: continue
                if op <= 0 or hi <= 0 or lo <= 0 or cl <= 0: continue
                date_str = f"{d_int // 10000}-{(d_int % 10000) // 100 :02d}-{d_int % 100 :02d}"
                dates.append(date_str)
                opens.append(float(op))
                highs.append(float(hi))
                lows.append(float(lo))
                closes.append(float(cl))
                volumes.append(float(vol))
                
        if len(dates) < 150: return None
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

# 3. Labeling Logic for Super Stocks
def label_stock_series(df, vni_df=None):
    """
    Identifies candidate breakout pivot points (T0) from a base:
    - Base consolidation: >= 25 trading sessions
    - T0: Close breaks out above 25-day rolling high with vol >= 1.4 * MA20(Vol) and Return >= 3.5%
    - Minimum liquidity: 20-day average volume >= 30,000 shares
    
    Evaluates forward performance (40 to 60 sessions):
    - MFE (Maximum Favorable Excursion): (Peak_Close - T0_Close) / T0_Close
    - MAE (Maximum Adverse Excursion): (Trough_Low - T0_Close) / T0_Close BEFORE hitting MFE peak
    - Stop loss hit: lowest low before peak <= -7.5%
    
    Label definitions:
    - Y = 1 (Super Stock): MFE >= +35% within 50 sessions AND MAE >= -7.5% before reaching peak.
    - Y = 0 (Negative Sample): Either Stop loss hit (MAE < -7.5%) within 20 sessions OR stagnant MFE < +12% in 40 sessions.
    """
    n = len(df)
    if n < 120:
        return []
        
    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    vols = df["volume"].values
    times = df["time"].values
    symbol = df["symbol"].iloc[0]
    
    # Precompute moving averages
    s_close = df["close"]
    s_vol = df["volume"]
    ma10 = s_close.rolling(10, min_periods=5).mean().values
    ma20 = s_close.rolling(20, min_periods=10).mean().values
    ma50 = s_close.rolling(50, min_periods=20).mean().values
    ma200 = s_close.rolling(200, min_periods=50).mean().values
    avg_vol20 = s_vol.rolling(20, min_periods=10).mean().values
    avg_vol50 = s_vol.rolling(50, min_periods=20).mean().values
    
    # 25-day rolling high of prior bars (exclude current bar)
    roll_high_25 = s_close.shift(1).rolling(25, min_periods=15).max().values
    roll_low_25 = s_close.shift(1).rolling(25, min_periods=15).min().values
    
    candidates = []
    
    # Scan from bar 60 to n - 50 (need 50 forward bars to evaluate outcome)
    # For recent bars (last 50 days), we can save them as 'unlabeled_recent' for real-time inference
    for i in range(50, n - 5):
        # 1. Liquidity check: avg_vol20 >= 30,000
        if avg_vol20[i] < 30000:
            continue
            
        c0 = closes[i]
        o0 = opens[i]
        h0 = highs[i]
        l0 = lows[i]
        v0 = vols[i]
        prev_c = closes[i - 1]
        
        chg_pct = (c0 - prev_c) / prev_c * 100.0 if prev_c > 0 else 0.0
        vol_ratio = v0 / avg_vol20[i] if avg_vol20[i] > 0 else 1.0
        
        # 2. Pivot Breakout Condition:
        # Close breaks above 25-day high OR 30-day resistance, strong surge candle
        prior_high = roll_high_25[i]
        if np.isnan(prior_high) or prior_high <= 0:
            continue
            
        is_breakout = (c0 >= prior_high * 0.99) and (chg_pct >= 3.0) and (vol_ratio >= 1.35)
        
        # Also include Pocket Pivot / SOS: Close > MA10, MA20, vol >= 1.8x MA20, chg >= 4%
        is_pocket_sos = (c0 > ma20[i]) and (chg_pct >= 4.0) and (vol_ratio >= 1.75) and (c0 >= roll_high_25[i] * 0.96)
        
        if not (is_breakout or is_pocket_sos):
            continue
            
        # Ensure we don't pick consecutive candidate bars within 10 days of each other for the same base
        if candidates and (i - candidates[-1]["bar_index"] < 10):
            # If the current bar is higher return, replace, else skip
            if chg_pct <= candidates[-1]["chg_pct"]:
                continue
            else:
                candidates.pop()
                
        # 3. Forward Outcome Evaluation (over next 50 trading days or up to end)
        forward_window = min(50, n - 1 - i)
        if forward_window < 15:
            # Too close to current date to label definitively
            target_label = -1
            mfe_pct = 0.0
            mae_pct = 0.0
            days_to_peak = 0
            stop_hit = 0
        else:
            forward_closes = closes[i + 1 : i + 1 + forward_window]
            forward_lows = lows[i + 1 : i + 1 + forward_window]
            forward_highs = highs[i + 1 : i + 1 + forward_window]
            
            # Find peak (MFE)
            peak_idx = np.argmax(forward_highs)
            peak_price = forward_highs[peak_idx]
            mfe_pct = (peak_price - c0) / c0 * 100.0
            days_to_peak = peak_idx + 1
            
            # Find trough (MAE) BEFORE the peak
            if peak_idx > 0:
                pre_peak_lows = forward_lows[:peak_idx]
                min_low_before_peak = np.min(pre_peak_lows)
            else:
                min_low_before_peak = forward_lows[0]
                
            mae_pct = (min_low_before_peak - c0) / c0 * 100.0
            
            # First 20 days minimum low to check for quick bulltrap failure
            first_20_low = np.min(forward_lows[:min(20, len(forward_lows))])
            first_20_mae = (first_20_low - c0) / c0 * 100.0
            
            stop_hit = 1 if (mae_pct <= -7.5) else 0
            
            # 4. Rigorous Labeling:
            # SUPER STOCK (Y = 1):
            # Gain >= +35% within 50 days AND Zero-Loss respected (MAE >= -7.5% before reaching peak)
            if mfe_pct >= 35.0 and mae_pct >= -7.5:
                target_label = 1
            # NEGATIVE SAMPLE (Y = 0):
            # Either hit stop loss within 20 days (Bulltrap) OR failed to achieve +12% in 40 days
            elif first_20_mae <= -7.5 or (mfe_pct < 12.0 and forward_window >= 35):
                target_label = 0
            else:
                # Ambiguous / Normal swing trade (+15% to +30%, or partial drawdown)
                # Keep as 0 for binary super-stock classification (only the elite count as 1)
                target_label = 0
                
        # Next-day bar for Day 2 validation features
        if i + 1 < n:
            c1 = closes[i + 1]
            o1 = opens[i + 1]
            l1 = lows[i + 1]
            h1 = highs[i + 1]
            v1 = vols[i + 1]
            day2_ret_pct = (c1 - c0) / c0 * 100.0
            day2_held_50pct = 1 if l1 >= (o0 + (c0 - o0) * 0.5) else 0
            day2_vol_ratio = v1 / avg_vol20[i + 1] if avg_vol20[i + 1] > 0 else 1.0
        else:
            day2_ret_pct = 0.0
            day2_held_50pct = 0
            day2_vol_ratio = 0.0

        candidates.append({
            "bar_index": i,
            "time": times[i],
            "symbol": symbol,
            "close": float(c0),
            "open": float(o0),
            "high": float(h0),
            "low": float(l0),
            "volume": float(v0),
            "chg_pct": float(chg_pct),
            "vol_ratio": float(vol_ratio),
            "mfe_pct": float(mfe_pct),
            "mae_pct": float(mae_pct),
            "days_to_peak": int(days_to_peak),
            "stop_hit": int(stop_hit),
            "target_label": int(target_label),
            "day2_ret_pct": float(day2_ret_pct),
            "day2_held_50pct": int(day2_held_50pct),
            "day2_vol_ratio": float(day2_vol_ratio)
        })
        
    return candidates

def run_labeling():
    t0 = time.time()
    print("==================================================================")
    print("🔥 BẮT ĐẦU QUÉT VÀ GÁN NHÃN SIÊU CỔ PHIẾU (SUPER STOCK LABELER) 🔥")
    print("==================================================================")
    
    files = glob.glob(os.path.join(METAKIT_STOCK_DIR, "*.dat"))
    print(f"Tổng số file cổ phiếu tìm thấy: {len(files)} files.")
    
    all_candidates = []
    processed_count = 0
    super_stock_count = 0
    
    # Process files
    for idx, fpath in enumerate(files):
        df_stock = parse_stock_dat(fpath)
        if df_stock is None or df_stock.empty:
            continue
            
        cands = label_stock_series(df_stock)
        if cands:
            for c in cands:
                if c["target_label"] == 1:
                    super_stock_count += 1
            all_candidates.extend(cands)
            
        processed_count += 1
        if (idx + 1) % 200 == 0:
            print(f"   Đã xử lý {idx + 1}/{len(files)} cổ phiếu... Tìm thấy {super_stock_count} điểm nổ Siêu Cổ Phiếu...")
            
    df_labels = pd.DataFrame(all_candidates)
    print(f"\n=> Hoàn tất quét trong {time.time() - t0:.2f}s!")
    print(f"=> Tổng số điểm bùng nổ/pivot được phát hiện: {len(df_labels):,}")
    
    # Distribution
    val_counts = df_labels["target_label"].value_counts().to_dict()
    print(f"=> Phân bổ nhãn:")
    print(f"   - Siêu Cổ Phiếu (Y = 1, MFE >= +35%, MAE >= -7.5%): {val_counts.get(1, 0):,} ({val_counts.get(1, 0)/len(df_labels)*100:.1f}%)")
    print(f"   - Breakout Bình thường / Thất bại (Y = 0): {val_counts.get(0, 0):,} ({val_counts.get(0, 0)/len(df_labels)*100:.1f}%)")
    print(f"   - Mới phát sinh gần đây (Chưa đủ 50 phiên để đóng nhãn): {val_counts.get(-1, 0):,}")
    
    # Sample top historical winners
    top_winners = df_labels[df_labels["target_label"] == 1].sort_values(by="mfe_pct", ascending=False).head(15)
    print("\n--- 15 ĐIỂM NỔ SIÊU CỔ PHIẾU HIỆU SUẤT CAO NHẤT TRONG LỊCH SỬ ---")
    for _, r in top_winners.iterrows():
        print(f"   * {r['symbol']:<5} | Ngày: {r['time']} | Lãi tối đa (MFE): +{r['mfe_pct']:.1f}% | Rũ bỏ nhỏ nhất (MAE): {r['mae_pct']:.1f}% | Đạt đỉnh sau {r['days_to_peak']} phiên")
        
    # Save output
    out_parquet = os.path.join(DATA_MART_DIR, "super_stock_training_labels.parquet")
    df_labels.to_parquet(out_parquet, index=False)
    print(f"\n=> Đã lưu nhãn huấn luyện tại: {out_parquet}")
    
    return df_labels

if __name__ == "__main__":
    run_labeling()
