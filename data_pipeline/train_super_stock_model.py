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
import lightgbm as lgb
import joblib
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score, classification_report, average_precision_score

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")
MODELS_DIR = os.path.join(DATA_MART_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

T0_FEATURE_COLS = [
    "rs_rating_60",
    "rs_rating_120",
    "vdu_ratio_20",
    "vol_up_down_ratio",
    "deposit_count_20",
    "obv_slope",
    "base_depth_pct",
    "vcp_ratio",
    "dist_to_52w_high",
    "is_near_52w_high",
    "close_vs_ma10",
    "close_vs_ma20",
    "close_vs_ma50",
    "close_vs_ma200",
    "ma_alignment_score",
    "t0_chg_pct",
    "t0_vol_ratio_ma20",
    "t0_vol_ratio_ma50",
    "t0_close_pos",
    "t0_upper_wick_ratio",
    "t0_spread_ratio",
    "tennis_ball_score",
    "sector_wave_score",
    "vni_regime",
    "vni_chg_pct",
    "vni_vs_ma20",
    "vni_vs_ma50"
]

VALIDATED_FEATURE_COLS = T0_FEATURE_COLS + [
    "day2_ret_pct",
    "day2_held_50pct",
    "day2_vol_ratio"
]

def train_and_evaluate(df_train, df_val, df_test, feature_cols, model_name, target_col="target_label"):
    print(f"\n-------------------------------------------------------------")
    print(f"🚀 HUẤN LUYỆN MÔ HÌNH: {model_name.upper()}")
    print(f"   Số đặc trưng đầu vào: {len(feature_cols)}")
    print(f"   Train samples: {len(df_train):,} | Val: {len(df_val):,} | Test (OOS): {len(df_test):,}")
    
    X_train = df_train[feature_cols].values
    y_train = df_train[target_col].values
    
    X_val = df_val[feature_cols].values
    y_val = df_val[target_col].values
    
    X_test = df_test[feature_cols].values
    y_test = df_test[target_col].values
    
    # Calculate scale pos weight for class imbalance (~12% positive)
    neg_count = np.sum(y_train == 0)
    pos_count = np.sum(y_train == 1)
    scale_pos = neg_count / max(1, pos_count)
    print(f"   Tỷ lệ nhãn Train: {pos_count} Super Stocks / {neg_count} Non-Super (Tỷ lệ 1:{scale_pos:.1f})")
    
    train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
    val_data = lgb.Dataset(X_val, label=y_val, feature_name=feature_cols, reference=train_data)
    
    params = {
        "objective": "binary",
        "metric": ["auc", "average_precision"],
        "boosting_type": "gbdt",
        "learning_rate": 0.035,
        "num_leaves": 31,
        "max_depth": 6,
        "min_child_samples": 25,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "scale_pos_weight": 2.2, # Moderate boost to focus on precision of top candidates
        "random_state": 42,
        "verbosity": -1,
        "force_col_wise": True
    }
    
    evals_result = {}
    model = lgb.train(
        params,
        train_data,
        num_boost_round=800,
        valid_sets=[train_data, val_data],
        valid_names=["train", "val"],
        callbacks=[
            lgb.early_stopping(stopping_rounds=40, verbose=False),
            lgb.record_evaluation(evals_result)
        ]
    )
    
    # Predict on Validation and Test
    val_preds_prob = model.predict(X_val, num_iteration=model.best_iteration)
    test_preds_prob = model.predict(X_test, num_iteration=model.best_iteration)
    
    val_auc = roc_auc_score(y_val, val_preds_prob)
    val_pr_auc = average_precision_score(y_val, val_preds_prob)
    test_auc = roc_auc_score(y_test, test_preds_prob)
    test_pr_auc = average_precision_score(y_test, test_preds_prob)
    
    print(f"\n   📊 KẾT QUẢ ĐO LƯỜNG:")
    print(f"   * Validation AUC: {val_auc:.4f} | PR-AUC: {val_pr_auc:.4f}")
    print(f"   * Test OOS (2024-2026) AUC: {test_auc:.4f} | PR-AUC: {test_pr_auc:.4f}")
    
    # Evaluate at high probability thresholds (>= 60%, >= 70%, >= 80%)
    print(f"\n   🎯 HIỆU QUẢ LỌC THEO NGƯỠNG XÁC SUẤT TRÊN TẬP TEST NGOÀI MẪU (2024-2026):")
    for thresh in [0.50, 0.65, 0.75, 0.80]:
        selected_mask = test_preds_prob >= thresh
        sel_count = np.sum(selected_mask)
        if sel_count > 0:
            true_super = np.sum((y_test == 1) & selected_mask)
            prec = true_super / sel_count * 100.0
            avg_mfe = df_test.loc[selected_mask, "mfe_pct"].mean()
            avg_mae = df_test.loc[selected_mask, "mae_pct"].mean()
            print(f"   * Xác suất >= {thresh*100:02.0f}%: Chọn {sel_count:>3} mã | Trúng Siêu Cổ Phiếu: {true_super:>3} ({prec:.1f}%) | Lãi TB MFE: +{avg_mfe:.1f}% | Rũ TB MAE: {avg_mae:.1f}%")
        else:
            print(f"   * Xác suất >= {thresh*100:02.0f}%: 0 mã được chọn.")
            
    # Feature Importance
    importance_gain = model.feature_importance(importance_type="gain")
    importance_split = model.feature_importance(importance_type="split")
    feat_imp = pd.DataFrame({
        "feature": feature_cols,
        "importance_gain": importance_gain,
        "importance_split": importance_split
    }).sort_values(by="importance_gain", ascending=False)
    
    print(f"\n   🏆 TOP 10 ĐẶC TRƯNG QUYẾT ĐỊNH SIÊU CỔ PHIẾU (THEO GAIN):")
    for rank, (_, row) in enumerate(feat_imp.head(10).iterrows(), 1):
        print(f"   {rank:>2}. {row['feature']:<22} | Gain: {row['importance_gain']:>8.1f} | Splits: {int(row['importance_split'])}")
        
    return model, {
        "val_auc": float(val_auc),
        "val_pr_auc": float(val_pr_auc),
        "test_auc": float(test_auc),
        "test_pr_auc": float(test_pr_auc),
        "best_iteration": int(model.best_iteration),
        "top_features": feat_imp.to_dict(orient="records")
    }

def run_training():
    t0 = time.time()
    print("==================================================================")
    print("🧠 BẮT ĐẦU HUẤN LUYỆN MÔ HÌNH HỌC MÁY DỰ ĐOÁN SIÊU CỔ PHIẾU 🧠")
    print("==================================================================")
    
    dataset_parquet = os.path.join(DATA_MART_DIR, "super_stock_features_dataset.parquet")
    if not os.path.exists(dataset_parquet):
        print(f"Lỗi: Không tìm thấy file {dataset_parquet}!")
        return
        
    df_all = pd.read_parquet(dataset_parquet)
    print(f"Đã nạp toàn bộ {len(df_all):,} mẫu đặc trưng.")
    
    # Filter out unlabeled recent samples (-1)
    df_valid = df_all[df_all["target_label"].isin([0, 1])].copy()
    print(f"Số mẫu có nhãn hoàn chỉnh: {len(df_valid):,} (Loại bỏ các mã mới nổ gần đây chưa đủ 50 ngày).")
    
    # Chronological Walk-Forward Split
    df_valid["time_dt"] = pd.to_datetime(df_valid["time"])
    
    train_mask = df_valid["time_dt"] <= pd.to_datetime("2020-12-31")
    val_mask = (df_valid["time_dt"] > pd.to_datetime("2020-12-31")) & (df_valid["time_dt"] <= pd.to_datetime("2023-12-31"))
    test_mask = df_valid["time_dt"] > pd.to_datetime("2023-12-31")
    
    df_train = df_valid[train_mask].copy().reset_index(drop=True)
    df_val = df_valid[val_mask].copy().reset_index(drop=True)
    df_test = df_valid[test_mask].copy().reset_index(drop=True)
    
    print(f"\nPhân chia dữ liệu Walk-Forward Time Series:")
    print(f"   1. Tập Train (2007 - 2020): {len(df_train):,} mẫu ({len(df_train[df_train['target_label']==1])} Super Stocks)")
    print(f"   2. Tập Validation (2021 - 2023): {len(df_val):,} mẫu ({len(df_val[df_val['target_label']==1])} Super Stocks)")
    print(f"   3. Tập Test OOS (2024 - 2026): {len(df_test):,} mẫu ({len(df_test[df_test['target_label']==1])} Super Stocks)")
    
    # 1. Train Model T0 (Realtime Breakout Radar)
    model_t0, rep_t0 = train_and_evaluate(
        df_train, df_val, df_test,
        T0_FEATURE_COLS,
        model_name="Model T0 - Quét Bùng Nổ Trong Phiên"
    )
    
    # Save Model T0
    model_t0_file = os.path.join(MODELS_DIR, "model_super_stock_t0.joblib")
    joblib.dump(model_t0, model_t0_file)
    print(f"\n=> Đã lưu Model T0 tại: {model_t0_file}")
    
    # 2. Train Model Validated (Day 2 Confirm - Pyramiding Scaling)
    model_val_t1, rep_t1 = train_and_evaluate(
        df_train, df_val, df_test,
        VALIDATED_FEATURE_COLS,
        model_name="Model Validated - Xác Nhận Cây Nến Thứ 2 (Day 2)"
    )
    
    # Save Model Validated
    model_t1_file = os.path.join(MODELS_DIR, "model_super_stock_validated.joblib")
    joblib.dump(model_val_t1, model_t1_file)
    print(f"\n=> Đã lưu Model Validated tại: {model_t1_file}")
    
    # Save metadata & feature list
    meta = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "t0_features": T0_FEATURE_COLS,
        "validated_features": VALIDATED_FEATURE_COLS,
        "model_t0_metrics": rep_t0,
        "model_validated_metrics": rep_t1
    }
    meta_file = os.path.join(MODELS_DIR, "super_stock_model_meta.json")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"=> Đã lưu thông số mô hình tại: {meta_file}")
    print(f"\n🎉 HOÀN TẤT TOÀN DIỆN HUẤN LUYỆN MACHINE LEARNING SIÊU CỔ PHIẾU ({time.time() - t0:.2f}s)!")

if __name__ == "__main__":
    run_training()
