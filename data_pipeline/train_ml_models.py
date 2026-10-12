import os
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import polars as pl
import pandas as pd
import numpy as np
import lightgbm as lgb
import joblib
import json
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")
MODELS_DIR = os.path.join(DATA_MART_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

FEATURE_COLS = [
    "spread_ratio",
    "close_pos",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "vol_ratio_ma10",
    "vol_ratio_ma20",
    "chg_pct",
    "rsi14",
    "ma_convergence",
    "close_vs_ma20",
    "close_vs_ma50",
    "close_vs_ma200",
    "base_20_spread_pct",
    "dry_supply_count_5",
    "dist_to_52w_high",
    "feat_is_52w_high",
    "sector_wave_score",
    "sec_pct_above_ma20",
    "sec_pct_above_ma50",
    "market_regime_code",
    "vni_vs_ma20",
    "vni_chg_pct"
]

def train_all_models():
    print("=== BẮT ĐẦU GIAI ĐOẠN 3: HUẤN LUYỆN MACHINE LEARNING 3 TẦNG ===")
    t0 = time.time()
    
    # 1. Load Data
    parquet_path = os.path.join(DATA_MART_DIR, "hose_3tiers_labeled_2007_2026.parquet")
    print(f"1. Đọc dữ liệu đã gán nhãn từ {parquet_path}...")
    df = pl.read_parquet(parquet_path)
    print(f"   Tổng số dòng nến: {len(df):,}")
    
    # Save feature names
    with open(os.path.join(MODELS_DIR, "feature_names.json"), "w") as f:
        json.dump(FEATURE_COLS, f, indent=2)
        
    # Split dates
    TRAIN_END = "2021-12-31"
    VAL_END = "2023-12-31"
    
    report = {
        "train_period": f"2007-01-01 -> {TRAIN_END}",
        "val_period": f"2022-01-01 -> {VAL_END}",
        "test_period": f"2024-01-01 -> 2026-09-22",
        "tiers": {}
    }
    
    # 2. Train and Evaluate each Tier
    tier_configs = [
        {
            "tier_key": "tier1_cuoc",
            "name": "Tầng 1: Điểm Mua Cược (Zero-Loss)",
            "cand_col": "cand_t1_flag",
            "label_col": "label_t1_cuoc",
            "model_file": "model_tier1_cuoc.joblib"
        },
        {
            "tier_key": "tier2_pocket",
            "name": "Tầng 2: Điểm Đẩy Nền (Pocket Pivot)",
            "cand_col": "cand_t2_flag",
            "label_col": "label_t2_pocket",
            "model_file": "model_tier2_pocket.joblib"
        },
        {
            "tier_key": "tier3_pivot",
            "name": "Tầng 3: Điểm Pivot / Breakout (Zero Đỉnh)",
            "cand_col": "cand_t3_flag",
            "label_col": "label_t3_pivot",
            "model_file": "model_tier3_pivot.joblib"
        }
    ]
    
    for cfg in tier_configs:
        t_key = cfg["tier_key"]
        t_name = cfg["name"]
        cand_col = cfg["cand_col"]
        label_col = cfg["label_col"]
        m_file = cfg["model_file"]
        
        print(f"\n-----------------------------------------------------------")
        print(f"Huấn luyện mô hình cho {t_name}...")
        
        # Filter valid labeled candidates
        df_sub = df.filter((pl.col(cand_col) == 1) & pl.col(label_col).is_not_null())
        
        df_train = df_sub.filter(pl.col("time") <= TRAIN_END)
        df_val = df_sub.filter((pl.col("time") > TRAIN_END) & (pl.col("time") <= VAL_END))
        df_test = df_sub.filter(pl.col("time") > VAL_END)
        
        print(f"  Số mẫu - Train (2007-2021): {len(df_train):,} | Val (2022-2023): {len(df_val):,} | Test Mù (2024-2026): {len(df_test):,}")
        
        X_train = df_train.select(FEATURE_COLS).to_numpy()
        y_train = df_train[label_col].to_numpy().astype(int)
        
        X_val = df_val.select(FEATURE_COLS).to_numpy()
        y_val = df_val[label_col].to_numpy().astype(int)
        
        X_test = df_test.select(FEATURE_COLS).to_numpy()
        y_test = df_test[label_col].to_numpy().astype(int)
        
        # LightGBM Dataset
        dtrain = lgb.Dataset(X_train, label=y_train, feature_name=FEATURE_COLS)
        dval = lgb.Dataset(X_val, label=y_val, feature_name=FEATURE_COLS, reference=dtrain)
        
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "boosting_type": "gbdt",
            "learning_rate": 0.03,
            "num_leaves": 31,
            "max_depth": 5,
            "min_data_in_leaf": 30,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": 42,
            "verbose": -1
        }
        
        # Train with early stopping
        model = lgb.train(
            params,
            dtrain,
            num_boost_round=300,
            valid_sets=[dtrain, dval],
            callbacks=[lgb.early_stopping(stopping_rounds=25, verbose=False)]
        )
        
        # Save model
        model_save_path = os.path.join(MODELS_DIR, m_file)
        joblib.dump(model, model_save_path)
        print(f"  Đã lưu mô hình: {model_save_path}")
        
        # Evaluate on Out-of-Sample Test Set (2024 - 2026)
        y_pred_test = model.predict(X_test)
        
        # Calculate baseline winrate
        test_total = len(y_test)
        base_winrate = float(np.mean(y_test) * 100) if test_total > 0 else 0.0
        
        # Evaluation by threshold
        thresh_results = {}
        for th in [0.40, 0.50, 0.55, 0.60, 0.65, 0.70]:
            mask = y_pred_test >= th
            count_signals = int(np.sum(mask))
            if count_signals > 0:
                win_rate = float(np.mean(y_test[mask]) * 100)
                win_count = int(np.sum(y_test[mask]))
                thresh_results[f"P >= {int(th*100)}%"] = {
                    "signals": count_signals,
                    "win_count": win_count,
                    "winrate_pct": round(win_rate, 2),
                    "improvement_pct": round(win_rate - base_winrate, 2)
                }
                
        # Feature Importance (Gain)
        importance = model.feature_importance(importance_type="gain")
        feat_imp = sorted(zip(FEATURE_COLS, importance), key=lambda x: x[1], reverse=True)
        top_features = [{"feature": f, "gain_pct": round(float(g / (sum(importance)+1e-9) * 100), 2)} for f, g in feat_imp[:8]]
        
        print(f"  --- KẾT QUẢ KIỂM ĐỊNH MÙ TRÊN TEST SET (2024 - 2026) ---")
        print(f"  * Tỷ lệ thắng cơ sở (Chưa lọc ML): {base_winrate:.2f}% ({np.sum(y_test)}/{test_total} lệnh)")
        if "P >= 60%" in thresh_results:
            r60 = thresh_results["P >= 60%"]
            print(f"  * Khi lọc bằng ML (Xác suất P >= 60%): {r60['winrate_pct']}% ({r60['win_count']}/{r60['signals']} lệnh) -> NÂNG CAO +{r60['improvement_pct']}%!")
        if "P >= 65%" in thresh_results:
            r65 = thresh_results["P >= 65%"]
            print(f"  * Khi lọc bằng ML (Xác suất P >= 65%): {r65['winrate_pct']}% ({r65['win_count']}/{r65['signals']} lệnh) -> NÂNG CAO +{r65['improvement_pct']}%!")
            
        print("  * Top đặc trưng đóng góp lớn nhất:")
        for tf in top_features[:5]:
            print(f"    + {tf['feature']}: {tf['gain_pct']}%")
            
        report["tiers"][t_key] = {
            "name": t_name,
            "test_total_signals": test_total,
            "baseline_winrate_pct": round(base_winrate, 2),
            "threshold_performance": thresh_results,
            "top_features": top_features
        }
        
    # Save Report
    report_file = os.path.join(DATA_MART_DIR, "ml_backtest_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        
    t1 = time.time()
    print(f"\n=== HOÀN THÀNH HUẤN LUYỆN TOÀN BỘ GIAI ĐOẠN 3 TRONG {t1 - t0:.2f} GIÂY ===")
    print(f"Báo cáo chi tiết đã lưu tại: {report_file}")

if __name__ == "__main__":
    train_all_models()
