import os
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import polars as pl
import numpy as np
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")

def build_features_and_labels():
    print("=== BẮT ĐẦU GIAI ĐOẠN 2: TRÍCH XUẤT ĐẶC TRƯNG & GÁN NHÃN 3 TẦNG ===")
    t0 = time.time()
    
    # 1. Load Parquet Data
    print("1. Đọc dữ liệu Big Data Mart...")
    stocks_path = os.path.join(DATA_MART_DIR, "hose_eod_2007_2026.parquet")
    vni_path = os.path.join(DATA_MART_DIR, "vnindex_regime_2007_2026.parquet")
    sector_path = os.path.join(DATA_MART_DIR, "sector_wave_matrix_2007_2026.parquet")
    
    df_stocks = pl.read_parquet(stocks_path)
    df_vni = pl.read_parquet(vni_path)
    df_sec = pl.read_parquet(sector_path)
    
    print(f"   Số dòng nến HOSE: {len(df_stocks):,}")
    print(f"   Số phiên VN-Index: {len(df_vni):,}")
    print(f"   Số bản ghi Sóng Ngành: {len(df_sec):,}")
    
    # 2. Join Market Regime from VN-Index
    print("2. Kết nối Chế độ Thị Trường VN-Index...")
    vni_subset = df_vni.select([
        pl.col("time"),
        pl.col("close").alias("vni_close"),
        pl.col("vni_chg_pct"),
        pl.col("market_regime"),
        ((pl.col("close") - pl.col("vni_ma20")) / (pl.col("vni_ma20") + 1e-9) * 100.0).alias("vni_vs_ma20")
    ])
    
    # Convert market_regime to numeric code: UPTREND=1, SIDEWAY=0, DOWNTREND=-1
    vni_subset = vni_subset.with_columns(
        pl.when(pl.col("market_regime") == "UPTREND").then(1)
        .when(pl.col("market_regime") == "DOWNTREND").then(-1)
        .otherwise(0).alias("market_regime_code")
    )
    
    df_joined = df_stocks.join(vni_subset, on="time", how="left")
    
    # 3. Join Sector Wave Matrix
    print("3. Kết nối Ma trận Sóng Ngành (Sector Wave Matrix)...")
    sec_subset = df_sec.select([
        pl.col("time"),
        pl.col("sector"),
        pl.col("pct_above_ma20").alias("sec_pct_above_ma20"),
        pl.col("pct_above_ma50").alias("sec_pct_above_ma50"),
        pl.col("sector_wave_score")
    ])
    
    df_joined = df_joined.join(sec_subset, on=["time", "sector"], how="left")
    
    # Fill missing sector scores for stocks tagged as KHAC
    df_joined = df_joined.with_columns([
        pl.col("sector_wave_score").fill_null(50.0),
        pl.col("sec_pct_above_ma20").fill_null(50.0),
        pl.col("sec_pct_above_ma50").fill_null(50.0),
        pl.col("market_regime_code").fill_null(0),
        pl.col("vni_vs_ma20").fill_null(0.0),
        pl.col("vni_chg_pct").fill_null(0.0)
    ])
    
    # 4. Feature Engineering per Symbol
    print("4. Tính toán Bộ Đặc Trưng VSA & Cấu Trúc Nền Giá (Vectorized)...")
    
    # Sort by symbol and time
    df_joined = df_joined.sort(["symbol", "time"])
    
    # Helper expressions partitioned by symbol
    prev_close = pl.col("close").shift(1).over("symbol")
    chg_pct = ((pl.col("close") - prev_close) / (prev_close + 1e-9) * 100.0).alias("chg_pct")
    
    spread = (pl.col("high") - pl.col("low")).alias("candle_spread")
    spread_ratio = (pl.col("spread") / (pl.col("avg_spread20") + 1e-9)).alias("spread_ratio")
    
    close_pos = ((pl.col("close") - pl.col("low")) / (pl.col("high") - pl.col("low") + 1e-9)).alias("close_pos")
    upper_wick = ((pl.col("high") - pl.max_horizontal("open", "close")) / (pl.col("high") - pl.col("low") + 1e-9)).alias("upper_wick_ratio")
    lower_wick = ((pl.min_horizontal("open", "close") - pl.col("low")) / (pl.col("high") - pl.col("low") + 1e-9)).alias("lower_wick_ratio")
    
    vol_ratio_ma10 = (pl.col("volume") / (pl.col("avg_vol10") + 1e-9)).alias("vol_ratio_ma10")
    vol_ratio_ma20 = (pl.col("volume") / (pl.col("avg_vol20") + 1e-9)).alias("vol_ratio_ma20")
    
    # MA Convergence
    ma_max = pl.max_horizontal("ma10", "ma20", "ma50")
    ma_min = pl.min_horizontal("ma10", "ma20", "ma50")
    ma_convergence = ((ma_max - ma_min) / (pl.col("ma20") + 1e-9) * 100.0).alias("ma_convergence")
    
    close_vs_ma20 = ((pl.col("close") - pl.col("ma20")) / (pl.col("ma20") + 1e-9) * 100.0).alias("close_vs_ma20")
    close_vs_ma50 = ((pl.col("close") - pl.col("ma50")) / (pl.col("ma50") + 1e-9) * 100.0).alias("close_vs_ma50")
    close_vs_ma200 = ((pl.col("close") - pl.col("ma200")) / (pl.col("ma200") + 1e-9) * 100.0).alias("close_vs_ma200")
    
    # Rolling metrics for base detection
    roll_min_close_10 = pl.col("close").rolling_min(10).over("symbol").alias("floor_price_base")
    roll_max_high_20 = pl.col("high").rolling_max(20).over("symbol").alias("roll_max_high_20")
    roll_min_low_20 = pl.col("low").rolling_min(20).over("symbol").alias("roll_min_low_20")
    base_20_spread = ((roll_max_high_20 - roll_min_low_20) / (roll_min_low_20 + 1e-9) * 100.0).alias("base_20_spread_pct")
    
    # Dry supply streak (Kiệt cung: Vol < 0.8 * TB10)
    is_dry = (pl.col("volume") < 0.8 * pl.col("avg_vol10")).cast(pl.Int32)
    dry_count_5 = is_dry.rolling_sum(5).over("symbol").alias("dry_supply_count_5")
    
    # 52-week High (250 sessions)
    roll_max_250 = pl.col("high").rolling_max(250).over("symbol").shift(1)
    dist_to_52w = ((roll_max_250 - pl.col("close")) / (roll_max_250 + 1e-9) * 100.0).alias("dist_to_52w_high")
    is_break_52w = (pl.col("close") >= roll_max_250).cast(pl.Int32).alias("feat_is_52w_high")
    
    df_feat = df_joined.with_columns([
        chg_pct,
        spread,
        spread_ratio,
        close_pos,
        upper_wick,
        lower_wick,
        vol_ratio_ma10,
        vol_ratio_ma20,
        ma_convergence,
        close_vs_ma20,
        close_vs_ma50,
        close_vs_ma200,
        roll_min_close_10,
        roll_max_high_20,
        roll_min_low_20,
        base_20_spread,
        dry_count_5,
        dist_to_52w,
        is_break_52w
    ])
    
    # 5. Target Labeling (Forward Looking)
    print("5. Gán Nhãn Mục Tiêu 3 Tầng theo chuẩn VSA Đậu Mầm...")
    
    # Forward Close values (T+1 to T+5)
    c1 = pl.col("close").shift(-1).over("symbol")
    c2 = pl.col("close").shift(-2).over("symbol")
    c3 = pl.col("close").shift(-3).over("symbol")
    c4 = pl.col("close").shift(-4).over("symbol")
    c5 = pl.col("close").shift(-5).over("symbol")
    c7 = pl.col("close").shift(-7).over("symbol")
    c10 = pl.col("close").shift(-10).over("symbol")
    
    min_fwd_5 = pl.min_horizontal(c1, c2, c3, c4, c5)
    max_fwd_5 = pl.max_horizontal(c1, c2, c3, c4, c5)
    max_fwd_7 = pl.max_horizontal(c1, c2, c3, c4, c5, c7)
    
    # ==================== TẦNG 1: ĐIỂM MUA CƯỢC 1/8 (Zero-Loss) ====================
    # Candidate Filter: MA convergence <= 6%, Nền 20 phiên <= 12%, Vol/TB10 <= 1.0, bám sát MA20
    is_cand_t1 = (
        (pl.col("ma_convergence") <= 6.5) &
        (pl.col("base_20_spread_pct") <= 14.0) &
        (pl.col("vol_ratio_ma10") <= 1.0) &
        (pl.col("close") >= pl.col("ma20") * 0.96)
    )
    
    # Quy tắc Zero-Loss người dùng:
    # 1. Trong T+1..T+5, giá không được đóng cửa dưới Floor (giá thấp nhất nền 10 phiên)
    # 2. Phải có ít nhất 1 phiên tăng >= +2.5% hoặc có nhịp đẩy
    zero_loss_pass = min_fwd_5 >= pl.col("floor_price_base")
    bounce_pass = max_fwd_5 >= pl.col("close") * 1.025
    
    label_t1 = (
        pl.when(is_cand_t1 & zero_loss_pass & bounce_pass).then(1)
        .when(is_cand_t1 & (~zero_loss_pass)).then(0)
        .otherwise(None)
    ).alias("label_t1_cuoc")
    
    # ==================== TẦNG 2: ĐIỂM ĐẨY NỀN POCKET PIVOT ====================
    # Candidate Filter: Nến xanh đóng nửa trên, vol 0.85x - 1.8x TB10, trên MA20, có nền trước đó
    is_cand_t2 = (
        (pl.col("chg_pct") >= 0.8) &
        (pl.col("close_pos") >= 0.65) &
        (pl.col("vol_ratio_ma10") >= 0.85) &
        (pl.col("vol_ratio_ma10") <= 1.8) &
        (pl.col("close") >= pl.col("ma20")) &
        (pl.col("dry_supply_count_5") >= 1)
    )
    
    # Success: Giữ được giá trên low cây nến nổ và tăng >= 4% trong T+3..T+7
    pocket_hold = min_fwd_5 >= pl.col("low")
    pocket_gain = max_fwd_7 >= pl.col("close") * 1.04
    
    label_t2 = (
        pl.when(is_cand_t2 & pocket_hold & pocket_gain).then(1)
        .when(is_cand_t2 & (~pocket_hold | ~pocket_gain)).then(0)
        .otherwise(None)
    ).alias("label_t2_pocket")
    
    # ==================== TẦNG 3: ĐIỂM PIVOT / BREAKOUT (Zero Đỉnh) ====================
    # Candidate Filter: Nến nổ >= +2.5%, vol >= 1.2x TB10, tiệm cận hoặc vượt đỉnh 20 phiên
    prev_max_high_20 = pl.col("roll_max_high_20").shift(1).over("symbol")
    is_cand_t3 = (
        (pl.col("chg_pct") >= 2.5) &
        (pl.col("close_pos") >= 0.70) &
        (pl.col("vol_ratio_ma10") >= 1.25) &
        (pl.col("close") >= prev_max_high_20 * 0.985)
    )
    
    # Quy tắc Zero Đỉnh người dùng:
    # 1. Ngay tại T+1 hoặc T+2 KHÔNG được gãy quá 50% thân nến bùng nổ
    half_candle = pl.col("low") + 0.5 * (pl.col("close") - pl.col("low"))
    zero_dinh_pass = (c1 >= half_candle) & (c2 >= half_candle)
    
    # 2. Sau phiên này 2 đến 5 ngày phải có lời (max T+2..T+5 > close nổ)
    profit_pass = pl.max_horizontal(c2, c3, c4, c5) > pl.col("close")
    
    label_t3 = (
        pl.when(is_cand_t3 & zero_dinh_pass & profit_pass).then(1)
        .when(is_cand_t3 & (~zero_dinh_pass | ~profit_pass)).then(0)
        .otherwise(None)
    ).alias("label_t3_pivot")
    
    # Thêm cờ ứng viên để dễ lọc tập mẫu
    is_cand_t1_flag = is_cand_t1.cast(pl.Int32).alias("cand_t1_flag")
    is_cand_t2_flag = is_cand_t2.cast(pl.Int32).alias("cand_t2_flag")
    is_cand_t3_flag = is_cand_t3.cast(pl.Int32).alias("cand_t3_flag")
    
    df_final = df_feat.with_columns([
        label_t1,
        label_t2,
        label_t3,
        is_cand_t1_flag,
        is_cand_t2_flag,
        is_cand_t3_flag
    ])
    
    # 6. Save Labeled Big Data Mart
    print("6. Lưu trữ Labeled Dataset vào file Parquet...")
    output_path = os.path.join(DATA_MART_DIR, "hose_3tiers_labeled_2007_2026.parquet")
    df_final.write_parquet(output_path, compression="snappy")
    
    t1 = time.time()
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"ĐÃ LƯU THÀNH CÔNG: {output_path} ({size_mb:.2f} MB)")
    print(f"Thời gian xử lý toàn bộ 1.4 triệu dòng: {t1 - t0:.2f} giây")
    
    # 7. Summary statistics
    stats = {
        "total_rows": len(df_final),
        "total_symbols": df_final["symbol"].n_unique(),
        "t1_candidates": int(df_final["cand_t1_flag"].sum()),
        "t1_success": int(df_final.filter(pl.col("label_t1_cuoc") == 1).height),
        "t1_fail": int(df_final.filter(pl.col("label_t1_cuoc") == 0).height),
        "t2_candidates": int(df_final["cand_t2_flag"].sum()),
        "t2_success": int(df_final.filter(pl.col("label_t2_pocket") == 1).height),
        "t2_fail": int(df_final.filter(pl.col("label_t2_pocket") == 0).height),
        "t3_candidates": int(df_final["cand_t3_flag"].sum()),
        "t3_success": int(df_final.filter(pl.col("label_t3_pivot") == 1).height),
        "t3_fail": int(df_final.filter(pl.col("label_t3_pivot") == 0).height),
    }
    
    # Calculate win rates
    stats["t1_winrate_pct"] = round(stats["t1_success"] / (stats["t1_success"] + stats["t1_fail"] + 1e-9) * 100, 2)
    stats["t2_winrate_pct"] = round(stats["t2_success"] / (stats["t2_success"] + stats["t2_fail"] + 1e-9) * 100, 2)
    stats["t3_winrate_pct"] = round(stats["t3_success"] / (stats["t3_success"] + stats["t3_fail"] + 1e-9) * 100, 2)
    
    summary_file = os.path.join(DATA_MART_DIR, "phase2_labeling_summary.json")
    import json
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
        
    print("\n=== KẾT QUẢ THỐNG KÊ GÁN NHÃN 3 TẦNG (2007 - 2026) ===")
    print(f"Tầng 1 (Điểm Mua Cược Zero-Loss): {stats['t1_candidates']:,} điểm | Thắng: {stats['t1_success']:,} ({stats['t1_winrate_pct']}%) | Thất bại: {stats['t1_fail']:,}")
    print(f"Tầng 2 (Điểm Đẩy Nền Pocket):      {stats['t2_candidates']:,} điểm | Thắng: {stats['t2_success']:,} ({stats['t2_winrate_pct']}%) | Thất bại: {stats['t2_fail']:,}")
    print(f"Tầng 3 (Điểm Pivot Zero Đỉnh):     {stats['t3_candidates']:,} điểm | Thắng: {stats['t3_success']:,} ({stats['t3_winrate_pct']}%) | Thất bại: {stats['t3_fail']:,}")
    print("=== HOÀN THÀNH TOÀN DIỆN GIAI ĐOẠN 2 ===")

if __name__ == "__main__":
    build_features_and_labels()
