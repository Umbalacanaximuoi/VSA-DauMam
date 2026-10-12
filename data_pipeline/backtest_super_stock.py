import os
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import time
import pandas as pd
import numpy as np
import joblib

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")
MODELS_DIR = os.path.join(DATA_MART_DIR, "models")

def run_backtest():
    print("==================================================================")
    print("📈 BẮT ĐẦU KIỂM ĐỊNH LỊCH SỬ THỰC CHIẾN (SUPER STOCK BACKTEST) 📈")
    print("==================================================================")
    
    # 1. Load Dataset
    feat_path = os.path.join(DATA_MART_DIR, "super_stock_features_dataset.parquet")
    df = pd.read_parquet(feat_path)
    df = df[df["target_label"].isin([0, 1])].copy()
    df["time_dt"] = pd.to_datetime(df["time"])
    
    # 2. Load Model & Features
    meta_path = os.path.join(MODELS_DIR, "super_stock_model_meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
        
    model_t1 = joblib.load(os.path.join(MODELS_DIR, "model_super_stock_validated.joblib"))
    features = meta["validated_features"]
    
    # 3. Predict Raw Probabilities
    raw_preds = model_t1.predict(df[features].values)
    df["raw_pred"] = raw_preds
    
    # 4. Calibrate into Percentile Score (0 - 100)
    # Using rank on the dataset
    df["super_stock_score"] = df["raw_pred"].rank(pct=True) * 100.0
    
    # Split into 3 Market Eras:
    # Era 1: 2007 - 2020 (Training era)
    # Era 2: 2021 - 2023 (Validation era - Covid Bull & 2022 Bear)
    # Era 3: 2024 - 2026 (Out-of-Sample Test era - Hiện tại)
    
    eras = [
        {"name": "GIAI ĐOẠN 2007 - 2020 (Lịch sử dài hạn)", "mask": df["time_dt"] <= pd.to_datetime("2020-12-31")},
        {"name": "GIAI ĐOẠN 2021 - 2023 (Sóng thần 2021 & Rũ bỏ 2022)", "mask": (df["time_dt"] > pd.to_datetime("2020-12-31")) & (df["time_dt"] <= pd.to_datetime("2023-12-31"))},
        {"name": "GIAI ĐOẠN 2024 - 2026 (Thực nghiệm Out-Of-Sample)", "mask": df["time_dt"] > pd.to_datetime("2023-12-31")},
        {"name": "TOÀN BỘ 20 NĂM LỊCH SỬ (2007 - 2026)", "mask": slice(None)}
    ]
    
    backtest_summary = {}
    
    for era in eras:
        name = era["name"]
        df_era = df[era["mask"]].copy()
        
        print(f"\n-------------------------------------------------------------")
        print(f"📊 KIỂM ĐỊNH HIỆU QUẢ: {name}")
        print(f"   Tổng số ứng viên breakout: {len(df_era):,}")
        
        # Test performance across thresholds: Baseline (Tất cả), Score >= 75, Score >= 85, Score >= 90
        thresholds = [0, 75, 85, 90]
        era_stats = []
        
        for th in thresholds:
            if th == 0:
                sub = df_era
                label = "Tất cả Breakout thị trường (Baseline)"
            else:
                sub = df_era[df_era["super_stock_score"] >= th]
                label = f"Hệ Thống Lọc Siêu Cổ Phiếu >= {th} Điểm"
                
            n_trades = len(sub)
            if n_trades == 0:
                continue
                
            # Simulate real-world trading rules:
            # 1. Stop loss: capped at -7.0% if mae_pct <= -7.5%
            # 2. Profit target: For super stocks, capture 70% of MFE (Trailing stop MA10/MA20)
            trade_returns = []
            wins = 0
            losses = 0
            gross_win = 0.0
            gross_loss = 0.0
            
            for _, r in sub.iterrows():
                mae = r["mae_pct"]
                mfe = r["mfe_pct"]
                
                # Did it breach -7.5% stop loss before hitting peak?
                if mae <= -7.5:
                    ret = -7.0 # Strict Zero-loss cut
                    losses += 1
                    gross_loss += abs(ret)
                else:
                    # Capturing trend via trailing stop: approx 75% of MFE peak
                    ret = max(0.0, mfe * 0.75)
                    if ret > 0:
                        wins += 1
                        gross_win += ret
                    else:
                        losses += 1
                        gross_loss += abs(ret)
                trade_returns.append(ret)
                
            trade_returns = np.array(trade_returns)
            win_rate = wins / n_trades * 100.0
            avg_ret = np.mean(trade_returns)
            avg_win = gross_win / max(1, wins)
            avg_loss = gross_loss / max(1, losses)
            rr_ratio = avg_win / max(0.1, avg_loss)
            profit_factor = gross_win / max(0.1, gross_loss)
            
            # Super stock detection rate (MFE >= +35% and no stop loss)
            super_count = (sub["target_label"] == 1).sum()
            super_rate = super_count / n_trades * 100.0
            
            print(f"\n   🎯 {label}:")
            print(f"      * Số lệnh kích hoạt: {n_trades:,} lệnh")
            print(f"      * Tỷ lệ trúng Siêu Cổ Phiếu thật: {super_count:,} mã ({super_rate:.1f}% vs baseline {df_era['target_label'].mean()*100:.1f}%)")
            print(f"      * Tỷ lệ thắng (Win Rate): {win_rate:.1f}%")
            print(f"      * Lãi trung bình / Lệnh: +{avg_ret:.2f}%")
            print(f"      * Tỷ lệ Lãi/Lỗ (Payoff R:R): {rr_ratio:.2f} : 1 (Lãi TB: +{avg_win:.1f}%, Cắt lỗ TB: -{avg_loss:.1f}%)")
            print(f"      * Hệ số Lợi Nhuận (Profit Factor): {profit_factor:.2f}")
            
            era_stats.append({
                "threshold": th,
                "label": label,
                "n_trades": int(n_trades),
                "super_count": int(super_count),
                "super_rate": float(super_rate),
                "win_rate": float(win_rate),
                "avg_return": float(avg_ret),
                "profit_factor": float(profit_factor),
                "rr_ratio": float(rr_ratio)
            })
            
        backtest_summary[name] = era_stats
        
    # Check iconic Vietnamese winners
    print(f"\n=============================================================")
    print(f"⭐ ĐIỂM SỐ CỦA CÁC SIÊU CỔ PHIẾU HUYỀN THOẠI TRONG LỊCH SỬ ⭐")
    print(f"=============================================================")
    iconic = ["DGC", "HPG", "HAH", "FRT", "VND", "SSI", "CEO", "VCS", "VGI", "CTR"]
    for sym in iconic:
        sub_sym = df[df["symbol"] == sym].sort_values(by="super_stock_score", ascending=False)
        if not sub_sym.empty:
            best = sub_sym.iloc[0]
            print(f"   * {sym:<4} | Ngày nổ: {best['time']} | Điểm Siêu CP: {best['super_stock_score']:.1f}/100 | Lãi MFE: +{best['mfe_pct']:.1f}% | Rũ MAE: {best['mae_pct']:.1f}% | Đạt đỉnh sau {int(best['days_to_peak'])} phiên")
            
    # Save Report to JSON
    report_file = os.path.join(DATA_MART_DIR, "super_stock_backtest_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(backtest_summary, f, indent=2, ensure_ascii=False)
    print(f"\n=> Đã lưu báo cáo backtest tại: {report_file}")

if __name__ == "__main__":
    run_backtest()
