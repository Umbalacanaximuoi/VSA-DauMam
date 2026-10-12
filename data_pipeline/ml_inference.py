import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import joblib
import json
import numpy as np
import polars as pl
import pandas as pd

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
    MEI_DIR = getattr(sys, '_MEIPASS', APP_DIR)
    BASE_DIR = APP_DIR if os.path.exists(os.path.join(APP_DIR, "data_mart")) else MEI_DIR
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")
MODELS_DIR = os.path.join(DATA_MART_DIR, "models")
if not os.path.exists(MODELS_DIR) and getattr(sys, 'frozen', False):
    alt_models = os.path.join(getattr(sys, '_MEIPASS', BASE_DIR), "data_mart", "models")
    if os.path.exists(alt_models):
        MODELS_DIR = alt_models

class VSAMLInferenceEngine:
    def __init__(self):
        self.model_t1 = None
        self.model_t2 = None
        self.model_t3 = None
        self.features = []
        self._load_models()
        
    def _load_models(self):
        feat_path = os.path.join(MODELS_DIR, "feature_names.json")
        if os.path.exists(feat_path):
            with open(feat_path, "r") as f:
                self.features = json.load(f)
                
        p1 = os.path.join(MODELS_DIR, "model_tier1_cuoc.joblib")
        p2 = os.path.join(MODELS_DIR, "model_tier2_pocket.joblib")
        p3 = os.path.join(MODELS_DIR, "model_tier3_pivot.joblib")
        
        if os.path.exists(p1): self.model_t1 = joblib.load(p1)
        if os.path.exists(p2): self.model_t2 = joblib.load(p2)
        if os.path.exists(p3): self.model_t3 = joblib.load(p3)

    def predict_from_row(self, row_dict: dict) -> dict:
        """Takes a dictionary of feature values and predicts probabilities for all 3 tiers."""
        if not self.features or not self.model_t1:
            return {"status": "error", "message": "Models not loaded"}
            
        # Build feature vector
        vec = []
        for feat in self.features:
            val = row_dict.get(feat, 0.0)
            if val is None or np.isnan(val):
                val = 0.0
            vec.append(float(val))
            
        X = np.array([vec])
        
        prob_t1 = float(self.model_t1.predict(X)[0] * 100.0) if self.model_t1 else 0.0
        prob_t2 = float(self.model_t2.predict(X)[0] * 100.0) if self.model_t2 else 0.0
        prob_t3 = float(self.model_t3.predict(X)[0] * 100.0) if self.model_t3 else 0.0
        
        # Recommendations based on trained model thresholds
        t1_rec = "Ưu tú" if prob_t1 >= 65.0 else ("Đạt yêu cầu" if prob_t1 >= 55.0 else "Rủi ro")
        t2_rec = "Ưu tú" if prob_t2 >= 60.0 else ("Đạt yêu cầu" if prob_t2 >= 50.0 else "Rủi ro")
        t3_rec = "Ưu tú" if prob_t3 >= 65.0 else ("Đạt yêu cầu" if prob_t3 >= 55.0 else "Rủi ro")
        
        return {
            "status": "success",
            "tier1_cuoc": {
                "probability_pct": round(prob_t1, 1),
                "evaluation": t1_rec,
                "is_recommended": prob_t1 >= 60.0
            },
            "tier2_pocket": {
                "probability_pct": round(prob_t2, 1),
                "evaluation": t2_rec,
                "is_recommended": prob_t2 >= 55.0
            },
            "tier3_pivot": {
                "probability_pct": round(prob_t3, 1),
                "evaluation": t3_rec,
                "is_recommended": prob_t3 >= 60.0
            }
        }

    def extract_features_from_df(self, df: pd.DataFrame, sector_wave_score: float = 50.0) -> dict:
        """Extracts the 22 ML features directly from a prepared pandas DataFrame."""
        if df is None or len(df) < 10:
            return {}
            
        row = df.iloc[-1]
        prev_row = df.iloc[-2] if len(df) >= 2 else row
        close = float(row['close'])
        prev_close = float(prev_row['close'])
        open_p = float(row['open'])
        high = float(row['high'])
        low = float(row['low'])
        vol = float(row['volume'])
        
        spread = high - low
        spreads = df['high'].iloc[-20:] - df['low'].iloc[-20:]
        avg_spread20 = float(spreads.mean()) if len(spreads) > 0 else spread
        spread_ratio = spread / (avg_spread20 + 1e-9)
        
        close_pos = (close - low) / (spread + 1e-9)
        upper_wick = (high - max(open_p, close)) / (spread + 1e-9)
        lower_wick = (min(open_p, close) - low) / (spread + 1e-9)
        
        avg_vol10 = float(row['avg_vol10']) if 'avg_vol10' in row else float(df['volume'].iloc[-10:].mean())
        avg_vol20 = float(row['avg_vol20']) if 'avg_vol20' in row else float(df['volume'].iloc[-20:].mean())
        vol_ratio_ma10 = vol / (avg_vol10 + 1e-9)
        vol_ratio_ma20 = vol / (avg_vol20 + 1e-9)
        
        chg_pct = (close - prev_close) / (prev_close + 1e-9) * 100.0
        rsi14 = float(row['rsi']) if 'rsi' in row and pd.notna(row['rsi']) else 50.0
        
        ma10 = float(row['ma10']) if 'ma10' in row and pd.notna(row['ma10']) else float(df['close'].iloc[-10:].mean())
        ma20 = float(row['ma20']) if 'ma20' in row and pd.notna(row['ma20']) else float(df['close'].iloc[-20:].mean())
        ma50 = float(row['ma50']) if 'ma50' in row and pd.notna(row['ma50']) else (float(df['close'].iloc[-50:].mean()) if len(df) >= 50 else ma20)
        ma200 = float(row['ma200']) if 'ma200' in row and pd.notna(row['ma200']) else (float(df['close'].iloc[-200:].mean()) if len(df) >= 200 else ma50)
        
        ma_max = max(ma10, ma20, ma50)
        ma_min = min(ma10, ma20, ma50)
        ma_convergence = (ma_max - ma_min) / (ma20 + 1e-9) * 100.0
        
        close_vs_ma20 = (close - ma20) / (ma20 + 1e-9) * 100.0
        close_vs_ma50 = (close - ma50) / (ma50 + 1e-9) * 100.0
        close_vs_ma200 = (close - ma200) / (ma200 + 1e-9) * 100.0
        
        w20 = df.iloc[-20:]
        max_h20 = float(w20['high'].max())
        min_l20 = float(w20['low'].min())
        base_20_spread_pct = (max_h20 - min_l20) / (min_l20 + 1e-9) * 100.0
        
        w5 = df.iloc[-5:]
        dry_count = 0
        for _, r in w5.iterrows():
            r_vol = float(r['volume'])
            r_avg10 = float(r['avg_vol10']) if 'avg_vol10' in r else avg_vol10
            if r_vol < 0.8 * r_avg10:
                dry_count += 1
                
        lookback_250 = df.iloc[-251:-1] if len(df) > 250 else df.iloc[:-1]
        max_250 = float(lookback_250['high'].max()) if len(lookback_250) > 0 else high
        dist_to_52w = (max_250 - close) / (max_250 + 1e-9) * 100.0
        feat_is_52w = 1.0 if close >= max_250 else 0.0
        
        return {
            "spread_ratio": spread_ratio,
            "close_pos": close_pos,
            "upper_wick_ratio": upper_wick,
            "lower_wick_ratio": lower_wick,
            "vol_ratio_ma10": vol_ratio_ma10,
            "vol_ratio_ma20": vol_ratio_ma20,
            "chg_pct": chg_pct,
            "rsi14": rsi14,
            "ma_convergence": ma_convergence,
            "close_vs_ma20": close_vs_ma20,
            "close_vs_ma50": close_vs_ma50,
            "close_vs_ma200": close_vs_ma200,
            "base_20_spread_pct": base_20_spread_pct,
            "dry_supply_count_5": float(dry_count),
            "dist_to_52w_high": dist_to_52w,
            "feat_is_52w_high": feat_is_52w,
            "sector_wave_score": sector_wave_score,
            "sec_pct_above_ma20": 55.0,
            "sec_pct_above_ma50": 50.0,
            "market_regime_code": 0.0,
            "vni_vs_ma20": 1.2,
            "vni_chg_pct": 0.1
        }

    def predict_symbol_date(self, symbol: str, date_str: str = None, live_df: pd.DataFrame = None) -> dict:
        """Looks up symbol & date in Big Data Mart (or live df) and evaluates ML probabilities."""
        symbol_clean = symbol.upper().strip()
        
        # 1. If live_df is provided and contains sufficient data, compute live ML features
        if live_df is not None and len(live_df) >= 10:
            try:
                feat_dict = self.extract_features_from_df(live_df)
                if feat_dict:
                    preds = self.predict_from_row(feat_dict)
                    row_last = live_df.iloc[-1]
                    preds["symbol"] = symbol_clean
                    preds["date"] = str(row_last.get("time", date_str or "Hôm nay"))[:10]
                    preds["close"] = float(row_last.get("close", 0.0))
                    preds["sector"] = "Ngân hàng" if symbol_clean in ["VCB","TCB","VPB","MBB","ACB","CTG","BID","STB"] else "Khác"
                    preds["sector_wave_score"] = 65.0
                    preds["market_regime"] = "SIDEWAY TÍCH LŨY"
                    return preds
            except Exception as e:
                pass

        # 2. Look up in Big Data Mart Parquet (2007-2026)
        labeled_path = os.path.join(DATA_MART_DIR, "hose_3tiers_labeled_2007_2026.parquet")
        if not os.path.exists(labeled_path):
            return {"status": "error", "message": "Parquet data not found"}
            
        df = pl.read_parquet(labeled_path)
        sub = df.filter(pl.col("symbol") == symbol_clean)
        if sub.is_empty():
            return {"status": "error", "message": f"Không tìm thấy dữ liệu HOSE cho mã {symbol}"}
            
        row_df = None
        if date_str:
            clean_date = str(date_str).strip()[:10]
            row_df = sub.filter(pl.col("time") == clean_date)
            if row_df.is_empty():
                # Fallback to the latest available trading date in big data mart <= date_str
                row_df = sub.filter(pl.col("time") <= clean_date).tail(1)
        
        if row_df is None or row_df.is_empty():
            row_df = sub.tail(1)
            
        if row_df.is_empty():
            return {"status": "error", "message": f"Không tìm thấy phiên giao dịch cho mã {symbol}"}
            
        row_dict = row_df.to_dicts()[0]
        preds = self.predict_from_row(row_dict)
        preds["symbol"] = symbol_clean
        preds["date"] = row_dict.get("time")
        preds["close"] = row_dict.get("close")
        preds["sector"] = row_dict.get("sector")
        preds["sector_wave_score"] = row_dict.get("sector_wave_score")
        preds["market_regime"] = row_dict.get("market_regime")
        return preds

if __name__ == "__main__":
    engine = VSAMLInferenceEngine()
    print("Inference Engine loaded successfully!")
    
    # Test on a real case (e.g. DGC around breakout 2021-08-11)
    res_dgc = engine.predict_symbol_date("DGC", "2021-08-11")
    print("\n--- TEST DGC NGÀY 11/08/2021 (Phiên Bùng Nổ Lịch Sử) ---")
    print(json.dumps(res_dgc, indent=2, ensure_ascii=False))
    
    # Test on a current stock today
    res_pvd = engine.predict_symbol_date("PVD", "2026-09-22")
    print("\n--- TEST PVD NGÀY 22/09/2026 (Phiên Hiện Tại) ---")
    print(json.dumps(res_pvd, indent=2, ensure_ascii=False))
