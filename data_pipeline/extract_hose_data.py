import os
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import struct
import datetime
import pandas as pd
import numpy as np
import polars as pl
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")
os.makedirs(DATA_MART_DIR, exist_ok=True)

METAKIT_STOCK_DIR = r"C:\MetakitData\AmiBroker\EOD\stock"
METAKIT_INDEX_DIR = r"C:\MetakitData\AmiBroker\EOD\index"

# Import sector map from evaluator
try:
    from evaluator import SYMBOL_SECTOR_LOOKUP as CORE_SECTOR_LOOKUP
except ImportError:
    CORE_SECTOR_LOOKUP = {}

FULL_SECTOR_LOOKUP = dict(CORE_SECTOR_LOOKUP)

# Enrich with vnstock industries
try:
    from vnstock import Listing
    l = Listing()
    df_ind = l.symbols_by_industries()
    for _, r in df_ind.iterrows():
        s = str(r.get('symbol', '')).strip().upper()
        ind_name = str(r.get('industry_name', '')).lower()
        if s and s not in FULL_SECTOR_LOOKUP:
            if 'ngân hàng' in ind_name: FULL_SECTOR_LOOKUP[s] = 'NGAN_HANG'
            elif 'tài chính' in ind_name or 'chứng khoán' in ind_name: FULL_SECTOR_LOOKUP[s] = 'CHUNG_KHOAN'
            elif 'bất động sản' in ind_name: FULL_SECTOR_LOOKUP[s] = 'BAT_DONG_SAN'
            elif 'thép' in ind_name or 'kim loại' in ind_name: FULL_SECTOR_LOOKUP[s] = 'THEP'
            elif 'dầu khí' in ind_name: FULL_SECTOR_LOOKUP[s] = 'DAU_KHI'
            elif 'bán lẻ' in ind_name: FULL_SECTOR_LOOKUP[s] = 'BAN_LE'
            elif 'hóa chất' in ind_name: FULL_SECTOR_LOOKUP[s] = 'HOA_CHAT'
            elif 'vận tải' in ind_name or 'cảng' in ind_name: FULL_SECTOR_LOOKUP[s] = 'CANG_BIEN'
except Exception:
    pass

def parse_dat_file(file_path: str, symbol: str) -> pd.DataFrame:
    """Parses binary .dat file from AmiBroker/Metakit into a DataFrame."""
    if not os.path.exists(file_path):
        return pd.DataFrame()
        
    try:
        with open(file_path, "rb") as f:
            header = f.read(32)
            if len(header) < 32:
                return pd.DataFrame()
            num_recs = struct.unpack("<I", header[:4])[0]
            if num_recs == 0:
                return pd.DataFrame()
                
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
                
                # Check date >= 20070101
                if date_int < 20070101:
                    continue
                    
                year = date_int // 10000
                month = (date_int % 10000) // 100
                day = date_int % 100
                
                # Basic sanity
                if year < 2007 or year > 2030 or month < 1 or month > 12 or day < 1 or day > 31:
                    continue
                if open_p <= 0 or high_p <= 0 or low_p <= 0 or close_p <= 0:
                    continue
                    
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                dates.append(date_str)
                opens.append(float(open_p))
                highs.append(float(high_p))
                lows.append(float(low_p))
                closes.append(float(close_p))
                volumes.append(float(vol))
                
        if not dates:
            return pd.DataFrame()
            
        df = pd.DataFrame({
            "time": dates,
            "symbol": symbol,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes
        })
        
        # Sort and drop duplicates
        df = df.drop_duplicates(subset=["time"]).sort_values(by="time").reset_index(drop=True)
        return df
    except Exception as e:
        return pd.DataFrame()

def process_single_stock(symbol: str) -> pd.DataFrame:
    file_path = os.path.join(METAKIT_STOCK_DIR, f"{symbol}.dat")
    df = parse_dat_file(file_path, symbol)
    if df.empty or len(df) < 20:
        return pd.DataFrame()
        
    # Pre-calculate rolling indicators
    df["ma10"] = df["close"].rolling(10).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()
    df["ma200"] = df["close"].rolling(200).mean()
    
    df["avg_vol10"] = df["volume"].rolling(10).mean()
    df["avg_vol20"] = df["volume"].rolling(20).mean()
    
    # RSI 14
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df["rsi14"] = 100.0 - (100.0 / (1.0 + rs))
    
    # Range / Spread
    df["spread"] = df["high"] - df["low"]
    df["avg_spread20"] = df["spread"].rolling(20).mean()
    
    # Add sector tag
    df["sector"] = FULL_SECTOR_LOOKUP.get(symbol, "KHAC")
    return df

def extract_all_hose_data():
    print("=== BẮT ĐẦU TRÍCH XUẤT BIG DATA SÀN HOSE (2007 - 2026) ===")
    
    # 1. Load HOSE symbols list
    symbols_file = os.path.join(DATA_MART_DIR, "hose_symbols.json")
    if os.path.exists(symbols_file):
        with open(symbols_file, "r", encoding="utf-8") as f:
            hose_symbols = json.load(f)
    else:
        hose_symbols = [f.replace(".dat", "") for f in os.listdir(METAKIT_STOCK_DIR) if f.endswith(".dat")]
        
    print(f"Tổng số mã HOSE cần xử lý: {len(hose_symbols)}")
    
    # 2. Multithreaded parsing
    dfs = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(process_single_stock, hose_symbols))
        
    for res in results:
        if not res.empty:
            dfs.append(res)
            
    print(f"Số mã có dữ liệu hợp lệ: {len(dfs)}")
    if not dfs:
        print("Lỗi: Không trích xuất được mã nào!")
        return
        
    combined_df = pd.concat(dfs, ignore_index=True)
    combined_df = combined_df.sort_values(by=["time", "symbol"]).reset_index(drop=True)
    
    print(f"Tổng số bản ghi nến HOSE (2007 - 2026): {len(combined_df):,} dòng")
    print(f"Khoảng thời gian: {combined_df['time'].min()} -> {combined_df['time'].max()}")
    
    # 3. Save to Parquet
    parquet_path = os.path.join(DATA_MART_DIR, "hose_eod_2007_2026.parquet")
    pl_df = pl.from_pandas(combined_df)
    pl_df.write_parquet(parquet_path, compression="snappy")
    
    size_mb = os.path.getsize(parquet_path) / (1024 * 1024)
    print(f"Đã lưu thành công file Parquet: {parquet_path} ({size_mb:.2f} MB)")
    
    # 4. Extract VN-INDEX & Market Regime
    extract_market_and_sector_matrix(combined_df)

def extract_market_and_sector_matrix(stocks_df: pd.DataFrame):
    print("\n=== XÂY DỰNG MA TRẬN SÓNG NGÀNH & VN-INDEX (2007 - 2026) ===")
    
    # Parse VNINDEX
    vnindex_file = os.path.join(METAKIT_INDEX_DIR, "VNINDEX.dat")
    df_vni = parse_dat_file(vnindex_file, "VNINDEX")
    if not df_vni.empty:
        df_vni["vni_ma20"] = df_vni["close"].rolling(20).mean()
        df_vni["vni_ma50"] = df_vni["close"].rolling(50).mean()
        df_vni["vni_ma200"] = df_vni["close"].rolling(200).mean()
        df_vni["vni_chg_pct"] = df_vni["close"].pct_change() * 100.0
        
        # Market Regime:
        # 1: Uptrend confirmed (Close > MA20 & MA20 > MA50)
        # 0: Sideway / Neutral
        # -1: Downtrend (Close < MA50)
        cond_up = (df_vni["close"] >= df_vni["vni_ma20"]) & (df_vni["vni_ma20"] >= df_vni["vni_ma50"])
        cond_down = (df_vni["close"] < df_vni["vni_ma50"])
        df_vni["market_regime"] = np.where(cond_up, "UPTREND", np.where(cond_down, "DOWNTREND", "SIDEWAY"))
        
        vni_parquet = os.path.join(DATA_MART_DIR, "vnindex_regime_2007_2026.parquet")
        pl.from_pandas(df_vni).write_parquet(vni_parquet, compression="snappy")
        print(f"Đã lưu VN-Index Regime Parquet: {len(df_vni)} phiên giao dịch")
    
    # Sector Breadth Matrix: Group by date and sector
    print("Tính toán độ rộng sóng ngành (Sector Breadth)...")
    valid_stocks = stocks_df[stocks_df["sector"] != "KHAC"].copy()
    
    # Metric 1: % stocks above MA20 in sector
    valid_stocks["above_ma20"] = (valid_stocks["close"] >= valid_stocks["ma20"]).astype(float)
    valid_stocks["above_ma50"] = (valid_stocks["close"] >= valid_stocks["ma50"]).astype(float)
    
    sector_summary = valid_stocks.groupby(["time", "sector"]).agg(
        total_stocks=("symbol", "count"),
        stocks_above_ma20=("above_ma20", "sum"),
        stocks_above_ma50=("above_ma50", "sum"),
        avg_spread_ratio=("spread", lambda x: np.mean(x)),
        total_volume=("volume", "sum")
    ).reset_index()
    
    sector_summary["pct_above_ma20"] = (sector_summary["stocks_above_ma20"] / (sector_summary["total_stocks"] + 1e-9)) * 100.0
    sector_summary["pct_above_ma50"] = (sector_summary["stocks_above_ma50"] / (sector_summary["total_stocks"] + 1e-9)) * 100.0
    
    # Sector Wave Score: 60% weight on % above MA20, 40% on % above MA50
    sector_summary["sector_wave_score"] = (0.6 * sector_summary["pct_above_ma20"] + 0.4 * sector_summary["pct_above_ma50"]).round(1)
    
    sector_parquet = os.path.join(DATA_MART_DIR, "sector_wave_matrix_2007_2026.parquet")
    pl.from_pandas(sector_summary).write_parquet(sector_parquet, compression="snappy")
    
    size_mb = os.path.getsize(sector_parquet) / (1024 * 1024)
    print(f"Đã lưu Sector Wave Matrix Parquet: {len(sector_summary):,} dòng ({size_mb:.2f} MB)")
    print("=== HOÀN THÀNH TOÀN DIỆN GIAI ĐOẠN 1 ===")

if __name__ == "__main__":
    extract_all_hose_data()
