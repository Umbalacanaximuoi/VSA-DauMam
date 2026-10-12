import os
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import logging
import pandas as pd
import numpy as np
import joblib
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")
MODELS_DIR = os.path.join(DATA_MART_DIR, "models")

try:
    from evaluator import get_prepared_stock_df, SYMBOL_SECTOR_LOOKUP, SECTOR_PEERS_MAP
except ImportError:
    SYMBOL_SECTOR_LOOKUP = {}
    SECTOR_PEERS_MAP = {}

class SuperStockEngine:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SuperStockEngine, cls).__new__(cls)
            cls._instance._init_models()
        return cls._instance
        
    def _init_models(self):
        self.model_t0 = None
        self.model_t1 = None
        self.meta = None
        self.t0_features = []
        self.validated_features = []
        
        meta_path = os.path.join(MODELS_DIR, "super_stock_model_meta.json")
        t0_model_path = os.path.join(MODELS_DIR, "model_super_stock_t0.joblib")
        t1_model_path = os.path.join(MODELS_DIR, "model_super_stock_validated.joblib")
        
        try:
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.meta = json.load(f)
                self.t0_features = self.meta.get("t0_features", [])
                self.validated_features = self.meta.get("validated_features", [])
                
            if os.path.exists(t0_model_path):
                self.model_t0 = joblib.load(t0_model_path)
            if os.path.exists(t1_model_path):
                self.model_t1 = joblib.load(t1_model_path)
                
            logging.info("SuperStockEngine: Đã tải thành công mô hình học máy Siêu Cổ Phiếu.")
        except Exception as e:
            logging.error(f"SuperStockEngine init error: {e}")

    def score_symbol(self, symbol: str, target_date_str: str = None, df: pd.DataFrame = None):
        symbol = symbol.upper().strip()
        if df is None or df.empty:
            try:
                df = get_prepared_stock_df(symbol, target_date_str)
            except Exception:
                return None
                
        if df is None or len(df) < 35:
            return None
            
        n = len(df)
        closes = df["close"].values
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        vols = df["volume"].values
        times = df["time"].values
        
        # Determine evaluation bar index
        target_idx = n - 1
        if target_date_str:
            target_str = str(target_date_str).strip()[:10]
            for idx, t in enumerate(times):
                if str(t)[:10] == target_str:
                    target_idx = idx
                    break
                    
        i = target_idx
        if i < 25:
            return None
            
        c0 = float(closes[i])
        o0 = float(opens[i])
        h0 = float(highs[i])
        l0 = float(lows[i])
        v0 = float(vols[i])
        prev_c = float(closes[i - 1]) if i > 0 else c0
        
        s_close = df["close"].iloc[:i + 1]
        s_vol = df["volume"].iloc[:i + 1]
        s_high = df["high"].iloc[:i + 1]
        s_low = df["low"].iloc[:i + 1]
        
        # Moving averages
        m10 = float(s_close.rolling(10, min_periods=5).mean().iloc[-1])
        m20 = float(s_close.rolling(20, min_periods=10).mean().iloc[-1])
        m50 = float(s_close.rolling(50, min_periods=20).mean().iloc[-1])
        m200 = float(s_close.rolling(200, min_periods=30).mean().iloc[-1])
        av20 = float(s_vol.rolling(20, min_periods=10).mean().iloc[-1])
        av50 = float(s_vol.rolling(50, min_periods=20).mean().iloc[-1])
        
        # Returns
        ret_60 = float(s_close.pct_change(60).iloc[-1] * 100.0) if len(s_close) >= 60 and not np.isnan(s_close.pct_change(60).iloc[-1]) else 0.0
        ret_120 = float(s_close.pct_change(120).iloc[-1] * 100.0) if len(s_close) >= 120 and not np.isnan(s_close.pct_change(120).iloc[-1]) else 0.0
        chg_pct = (c0 - prev_c) / prev_c * 100.0 if prev_c > 0 else 0.0
        
        # ATR 5 and ATR 20
        prev_closes = s_close.shift(1).fillna(s_close)
        tr = np.maximum(s_high - s_low, np.maximum(np.abs(s_high - prev_closes), np.abs(s_low - prev_closes)))
        atr5 = float(tr.rolling(5, min_periods=3).mean().iloc[-1]) if len(tr) >= 5 else 1.0
        atr20 = float(tr.rolling(20, min_periods=10).mean().iloc[-1]) if len(tr) >= 20 else 1.0
        vcp_ratio = float(atr5 / (atr20 + 1e-5))
        
        # VDU in prior 20 bars
        prior_vols = vols[max(0, i - 20):i]
        prior_av20 = av20
        vdu_count = np.sum(prior_vols < (prior_av20 * 0.85)) if len(prior_vols) > 0 else 0
        vdu_ratio_20 = float(vdu_count / len(prior_vols) * 100.0) if len(prior_vols) > 0 else 0.0
        
        prior_closes = closes[max(0, i - 20):i]
        prior_opens = opens[max(0, i - 20):i]
        up_mask = prior_closes >= prior_opens
        vol_up = np.sum(prior_vols[up_mask]) if len(prior_vols) > 0 else 1.0
        vol_down = np.sum(prior_vols[~up_mask]) if len(prior_vols) > 0 else 1.0
        vol_up_down_ratio = float(vol_up / (vol_down + 1e-5))
        
        # Deposit count
        deposit_mask = (prior_vols >= (prior_av20 * 1.4)) & up_mask
        deposit_count_20 = int(np.sum(deposit_mask)) if len(prior_vols) > 0 else 0
        
        # Base Depth
        prior_highs = highs[max(0, i - 25):i]
        prior_lows = lows[max(0, i - 25):i]
        base_max = float(np.max(prior_highs)) if len(prior_highs) > 0 else c0
        base_min = float(np.min(prior_lows)) if len(prior_lows) > 0 else c0
        base_depth_pct = (base_max - base_min) / (base_max + 1e-5) * 100.0
        
        # 52w High
        h250 = float(s_high.rolling(250, min_periods=30).max().iloc[-1]) if len(s_high) >= 30 else c0
        dist_to_52w_high = (c0 - h250) / h250 * 100.0
        is_near_52w_high = 1 if dist_to_52w_high >= -5.0 else 0
        
        # OBV slope
        direction = np.sign(s_close.diff().fillna(0).values)
        obv = np.cumsum(direction * vols[:i + 1])
        s_obv = pd.Series(obv)
        obv_ma10 = float(s_obv.rolling(10, min_periods=5).mean().iloc[-1]) if len(s_obv) >= 5 else float(obv[-1])
        obv_slope = float((obv[-1] - obv_ma10) / (abs(obv_ma10) + 1e-5) * 100.0)
        
        # Candle parameters
        candle_range = h0 - l0
        t0_close_pos = float((c0 - l0) / (candle_range + 1e-5))
        t0_upper_wick_ratio = float((h0 - max(o0, c0)) / (candle_range + 1e-5))
        t0_spread_ratio = float(candle_range / (atr20 + 1e-5))
        t0_vol_ratio_ma20 = float(v0 / (av20 + 1e-5))
        t0_vol_ratio_ma50 = float(v0 / (av50 + 1e-5))
        
        close_vs_ma10 = (c0 / m10 - 1.0) * 100.0 if m10 > 0 else 0.0
        close_vs_ma20 = (c0 / m20 - 1.0) * 100.0 if m20 > 0 else 0.0
        close_vs_ma50 = (c0 / m50 - 1.0) * 100.0 if m50 > 0 else 0.0
        close_vs_ma200 = (c0 / m200 - 1.0) * 100.0 if m200 > 0 else 0.0
        ma_alignment = 1 if (m10 > m20 and m20 > m50 and c0 > m200) else 0
        
        # Market context placeholder / defaults
        sector = SYMBOL_SECTOR_LOOKUP.get(symbol, "OTHER")
        sector_wave_score = 65.0
        vni_regime = 1
        vni_chg_pct = 0.5
        vni_vs_ma20 = 2.0
        vni_vs_ma50 = 3.5
        tennis_ball_score = float((c0 - base_max) / (base_max + 1e-5) * 100.0 - (-3.0))
        rs_rating_60 = float(ret_60 - 5.0)
        rs_rating_120 = float(ret_120 - 8.0)
        
        # Check if Day 2 bar exists
        has_day2 = (i + 1 < n)
        if has_day2:
            c1 = float(closes[i + 1])
            l1 = float(lows[i + 1])
            v1 = float(vols[i + 1])
            day2_ret_pct = (c1 - c0) / c0 * 100.0
            day2_held_50pct = 1 if l1 >= (o0 + (c0 - o0) * 0.5) else 0
            day2_vol_ratio = float(v1 / (av20 + 1e-5))
        else:
            day2_ret_pct = 0.0
            day2_held_50pct = 1 if t0_close_pos >= 0.70 else 0
            day2_vol_ratio = 1.0

        # Build feature vector
        feat_dict = {
            "rs_rating_60": rs_rating_60,
            "rs_rating_120": rs_rating_120,
            "vdu_ratio_20": vdu_ratio_20,
            "vol_up_down_ratio": vol_up_down_ratio,
            "deposit_count_20": deposit_count_20,
            "obv_slope": obv_slope,
            "base_depth_pct": base_depth_pct,
            "vcp_ratio": vcp_ratio,
            "dist_to_52w_high": dist_to_52w_high,
            "is_near_52w_high": is_near_52w_high,
            "close_vs_ma10": close_vs_ma10,
            "close_vs_ma20": close_vs_ma20,
            "close_vs_ma50": close_vs_ma50,
            "close_vs_ma200": close_vs_ma200,
            "ma_alignment_score": ma_alignment,
            "t0_chg_pct": chg_pct,
            "t0_vol_ratio_ma20": t0_vol_ratio_ma20,
            "t0_vol_ratio_ma50": t0_vol_ratio_ma50,
            "t0_close_pos": t0_close_pos,
            "t0_upper_wick_ratio": t0_upper_wick_ratio,
            "t0_spread_ratio": t0_spread_ratio,
            "tennis_ball_score": tennis_ball_score,
            "sector_wave_score": sector_wave_score,
            "vni_regime": vni_regime,
            "vni_chg_pct": vni_chg_pct,
            "vni_vs_ma20": vni_vs_ma20,
            "vni_vs_ma50": vni_vs_ma50,
            "day2_ret_pct": day2_ret_pct,
            "day2_held_50pct": day2_held_50pct,
            "day2_vol_ratio": day2_vol_ratio
        }
        
        # Inference
        score = 50.0
        if has_day2 and self.model_t1 is not None and self.validated_features:
            x = np.array([[feat_dict[k] for k in self.validated_features]])
            raw_p = float(self.model_t1.predict(x)[0])
            # Mapping 0.10 -> 0.33 to 0 -> 100
            score = float(np.clip((raw_p - 0.11) / (0.28 - 0.11) * 100.0, 5.0, 99.5))
        elif self.model_t0 is not None and self.t0_features:
            x = np.array([[feat_dict[k] for k in self.t0_features]])
            raw_p = float(self.model_t0.predict(x)[0])
            score = float(np.clip((raw_p - 0.11) / (0.28 - 0.11) * 100.0, 5.0, 99.5))
            
        # Classify Tier
        if score >= 85.0:
            tier_badge = "💎 SIÊU CỔ PHIẾU KIM CƯƠNG"
            tier_code = "DIAMOND"
            expected_mfe = "+45% đến +80%"
        elif score >= 70.0:
            tier_badge = "🥇 TIỀM NĂNG CAO"
            tier_code = "GOLD"
            expected_mfe = "+30% đến +50%"
        elif score >= 50.0:
            tier_badge = "🟡 THEO DÕI NỀN"
            tier_code = "SILVER"
            expected_mfe = "+15% đến +25%"
        else:
            tier_badge = "⚪ TRUNG BÌNH / BỎ QUA"
            tier_code = "BRONZE"
            expected_mfe = "< +15%"
            
        # 5 Pillars Breakdown
        pillars = {
            "gio_dong": {
                "name": "Gió Đông (VN-Index Macro)",
                "score": 85 if vni_regime == 1 else (60 if vni_regime == 0 else 30),
                "status": "Thuận lợi (Uptrend)" if vni_regime == 1 else "Phân hóa (Sideway)"
            },
            "dan_soi": {
                "name": "Thuyết Đàn Sói (Sóng Ngành)",
                "score": round(sector_wave_score, 1),
                "status": f"Dòng {sector} bảo trợ"
            },
            "nen_gia": {
                "name": "Nền Giá & Cạn Cung (VDU / VCP)",
                "score": min(95, round(vdu_ratio_20 * 1.2 + (1.0 - vcp_ratio) * 30 + 30, 1)),
                "status": f"Kiệt cung {vdu_ratio_20:.0f}%, VCP {vcp_ratio:.2f}"
            },
            "xung_luc": {
                "name": "Xung Lực Đột Biến (SOS Surge)",
                "score": min(98, round(t0_close_pos * 40 + min(3.0, t0_vol_ratio_ma20) * 18, 1)),
                "status": f"Vol x{t0_vol_ratio_ma20:.1f}, Đóng {t0_close_pos*100:.0f}% đỉnh"
            },
            "tennis_ball": {
                "name": "Quả Bóng Tennis & Cây Nến Thứ 2",
                "score": min(95, round(85 if day2_held_50pct else 45 + day2_ret_pct * 3, 1)),
                "status": "Giữ vững >50% thân nến (Zero-Đỉnh)" if day2_held_50pct else "Chờ test cung"
            }
        }
        
        # Capital Allocation Plan
        capital_plan = {
            "entry_bet": "Giải ngân Cược 30 - 40% vị thế tiền mặt tại điểm Pivot/Nền số 2",
            "entry_scale": "Gia tăng Kim Tự Tháp 30 - 40% khi Cây nến thứ 2 (Day 2) xác nhận xanh",
            "stop_loss": f"Cắt lỗ tuyệt đối Zero-Loss tại {round(c0 * 0.93, 2):,} (-7.0%) - Không thương lượng",
            "target": f"Mục tiêu sóng {expected_mfe} (Kỳ vọng vùng {round(c0 * 1.40, 2):,} - {round(c0 * 1.60, 2):,})",
            "margin_trigger": "Chỉ kích hoạt Margin khi danh mục đã có đệm lãi an toàn >= +10%"
        }
        
        return {
            "symbol": symbol,
            "time": str(times[i]),
            "close": round(c0, 2),
            "chg_pct": round(chg_pct, 2),
            "volume": int(v0),
            "vol_ratio": round(t0_vol_ratio_ma20, 2),
            "sector": sector,
            "super_stock_score": round(score, 1),
            "tier_badge": tier_badge,
            "tier_code": tier_code,
            "expected_mfe": expected_mfe,
            "pillars": pillars,
            "capital_plan": capital_plan,
            "features_summary": {
                "rs_rating_60": round(rs_rating_60, 1),
                "vdu_ratio_20": round(vdu_ratio_20, 1),
                "deposit_count": deposit_count_20,
                "dist_to_52w_high": round(dist_to_52w_high, 1),
                "day2_held_50pct": day2_held_50pct
            }
        }

    def scan_radar(self, symbols_list: list = None, target_date_str: str = None, min_score: float = 65.0):
        if not symbols_list:
            from evaluator import SECTOR_PEERS_MAP
            all_syms = set()
            for peers in SECTOR_PEERS_MAP.values():
                all_syms.update(peers)
            # Add notable market leaders
            all_syms.update(["DGC", "HPG", "HAH", "FRT", "VND", "SSI", "VCS", "VGI", "CTR", "FPT", "MWG", "PNJ", "GVR", "TCB", "MBB", "STB", "VIX", "KBC", "PDR", "DIG", "NLG"])
            symbols_list = sorted(list(all_syms))
            
        results = []
        def eval_one(s):
            try:
                res = self.score_symbol(s, target_date_str)
                if res and res.get("super_stock_score", 0) >= min_score:
                    return res
            except Exception:
                pass
            return None
            
        with ThreadPoolExecutor(max_workers=8) as executor:
            scanned = list(executor.map(eval_one, symbols_list))
            
        results = [r for r in scanned if r is not None]
        results.sort(key=lambda x: x["super_stock_score"], reverse=True)
        return results

# Singleton helper
_engine = None
def get_super_stock_engine() -> SuperStockEngine:
    global _engine
    if _engine is None:
        _engine = SuperStockEngine()
    return _engine
