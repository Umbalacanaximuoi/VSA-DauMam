import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import polars as pl
import pandas as pd
import numpy as np

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
    MEI_DIR = getattr(sys, '_MEIPASS', APP_DIR)
    BASE_DIR = APP_DIR if os.path.exists(os.path.join(APP_DIR, "data_mart")) else MEI_DIR
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")
HUB_DIR = os.path.join(BASE_DIR, "tai_lieu_hoc_may_vsa", "02_so_tay_mau_hinh_vsa")
if not os.path.exists(HUB_DIR) and getattr(sys, 'frozen', False):
    alt_hub = os.path.join(getattr(sys, '_MEIPASS', BASE_DIR), "tai_lieu_hoc_may_vsa", "02_so_tay_mau_hinh_vsa")
    if os.path.exists(alt_hub):
        HUB_DIR = alt_hub

EXCEL_PATH = os.path.join(HUB_DIR, "so_tay_mau_hinh_vsa.xlsx")
CSV_PATH = os.path.join(HUB_DIR, "so_tay_mau_hinh_vsa.csv")
LABELED_PARQUET = os.path.join(DATA_MART_DIR, "hose_3tiers_labeled_2007_2026.parquet")
if not os.path.exists(LABELED_PARQUET) and getattr(sys, 'frozen', False):
    alt_p = os.path.join(getattr(sys, '_MEIPASS', BASE_DIR), "data_mart", "hose_3tiers_labeled_2007_2026.parquet")
    if os.path.exists(alt_p):
        LABELED_PARQUET = alt_p

class VSAPatternMatcher:
    def __init__(self):
        self.df_data = None
        self.golden_patterns = []
        self._load_data()
        self._load_golden_cases()
        
    def _load_data(self):
        if os.path.exists(LABELED_PARQUET):
            self.df_data = pl.read_parquet(LABELED_PARQUET)
            supp_p = os.path.join(DATA_MART_DIR, "supplementary_symbols.parquet")
            if os.path.exists(supp_p):
                try:
                    df_supp = pl.read_parquet(supp_p)
                    for c in self.df_data.columns:
                        if c not in df_supp.columns:
                            df_supp = df_supp.with_columns(pl.lit(0).alias(c))
                    df_supp = df_supp.select(self.df_data.columns).cast(self.df_data.schema)
                    self.df_data = pl.concat([self.df_data, df_supp])
                except Exception:
                    pass
            
    def _load_golden_cases(self):
        def _norm_date(val):
            if pd.isna(val) or not str(val).strip():
                return ""
            try:
                return pd.to_datetime(val).strftime('%Y-%m-%d')
            except Exception:
                return str(val).strip()[:10]

        df_excel = None
        fallback_excel = os.path.join(BASE_DIR, "so_tay_mau_hinh_vsa.xlsx")
        fallback_csv = os.path.join(BASE_DIR, "so_tay_mau_hinh_vsa.csv")
        
        for p in [EXCEL_PATH, fallback_excel]:
            if os.path.exists(p):
                try:
                    df_excel = pd.read_excel(p)
                    break
                except Exception:
                    pass
                    
        if df_excel is None:
            for p in [CSV_PATH, fallback_csv]:
                if os.path.exists(p):
                    try:
                        df_excel = pd.read_csv(p)
                        break
                    except Exception:
                        pass
                
        if df_excel is not None and not df_excel.empty:
            for _, r in df_excel.iterrows():
                sym = str(r.get("Ma_CP", "")).strip().upper()
                name = str(r.get("Ten_Mau_Hinh", "Chưa đặt tên"))
                start_d = _norm_date(r.get("Ngay_Bat_Dau_Nen"))
                cuoc_d = _norm_date(r.get("Ngay_Diem_Cuoc"))
                pocket_d = _norm_date(r.get("Ngay_Pocket"))
                pivot_d = _norm_date(r.get("Ngay_Pivot_Breakout"))
                res = str(r.get("Ket_Qua", "Thành công"))
                note = str(r.get("Ghi_Chu_Dac_Diem", ""))
                img_file = str(r.get("File_Anh_Bieu_Do", "")).strip() if pd.notna(r.get("File_Anh_Bieu_Do")) else ""
                img_ind = str(r.get("Dac_Diem_Chi_Bao_Tren_Anh", "")).strip() if pd.notna(r.get("Dac_Diem_Chi_Bao_Tren_Anh")) else ""
                
                if sym and start_d:
                    end_d = pivot_d or pocket_d or cuoc_d or start_d
                    self.golden_patterns.append({
                        "symbol": sym,
                        "name": name,
                        "pattern_name": name,
                        "start_date": start_d,
                        "end_date": end_d,
                        "cuoc_date": cuoc_d,
                        "pocket_date": pocket_d,
                        "pivot_date": pivot_d,
                        "result": res,
                        "note": note,
                        "image_file": img_file,
                        "image_indicators": img_ind
                    })
                    
        # 2. Tự động nạp mẫu hình từ kho ảnh trực quan (03_hinh_mau_bieu_do & mau_hinh_anh)
        image_dirs = [
            os.path.join(BASE_DIR, "tai_lieu_hoc_may_vsa", "03_hinh_mau_bieu_do"),
            os.path.join(BASE_DIR, "mau_hinh_anh")
        ]
        import glob
        import re
        for idir in image_dirs:
            if not os.path.exists(idir):
                continue
            img_files = glob.glob(os.path.join(idir, "*.*"))
            for img_p in img_files:
                ext = os.path.splitext(img_p)[1].lower()
                if ext not in [".png", ".jpg", ".jpeg", ".bmp", ".webp"]:
                    continue
                base_fn = os.path.basename(img_p)
                # Check if already registered via Excel/CSV
                if any(g.get("image_file") == base_fn for g in self.golden_patterns):
                    continue
                    
                # Format 1: Ten_Mau_Hinh(CP2025).png ví dụ Vuot_can_cheo(VIX2025).png
                m = re.match(r"^([a-zA-Z0-9_]+)\(([A-Z]{3})(\d{4})\)", base_fn)
                if m:
                    pat_name, sym, year = m.group(1).replace("_", " "), m.group(2), m.group(3)
                    start_d = f"{year}-01-01"
                    end_d = f"{year}-12-31"
                    if self.df_data is not None:
                        dates = self.df_data.filter((pl.col("symbol") == sym) & (pl.col("time").str.starts_with(year)))["time"].to_list()
                        if dates:
                            start_d = dates[0]
                            end_d = dates[len(dates) // 2]
                    self.golden_patterns.append({
                        "symbol": sym,
                        "name": f"Ảnh: {pat_name} ({sym} {year})",
                        "start_date": start_d,
                        "end_date": end_d,
                        "cuoc_date": "",
                        "pocket_date": "",
                        "pivot_date": end_d,
                        "result": "Mẫu hình trực quan thực chiến",
                        "note": f"Nhận diện tự động từ tệp ảnh: {base_fn}",
                        "image_file": base_fn,
                        "image_indicators": "Chỉ báo RSI, MACD, OBV WMA10 được đánh dấu trên biểu đồ"
                    })
                    continue
                    
                # Format 2: SYM_START_END_NAME.png
                parts = os.path.splitext(base_fn)[0].split("_")
                if len(parts) >= 3 and len(parts[0]) == 3 and parts[0].isalpha():
                    sym = parts[0].upper().strip()
                    start_d = parts[1].strip()
                    end_d = parts[2].strip()
                    pat_name = "_".join(parts[3:]).strip() if len(parts) >= 4 else "Mẫu hình trực quan"
                    self.golden_patterns.append({
                        "symbol": sym,
                        "name": f"Ảnh: {pat_name}",
                        "start_date": start_d,
                        "end_date": end_d,
                        "cuoc_date": "",
                        "pocket_date": "",
                        "pivot_date": end_d,
                        "result": "Đã lưu từ biểu đồ thực chiến",
                        "note": f"Khớp dạng sóng từ ảnh biểu đồ: {base_fn}",
                        "image_file": base_fn,
                        "image_indicators": ""
                    })

    def extract_fingerprint(self, symbol: str, end_date: str, lookback: int = 25) -> np.ndarray:
        """Extracts normalized price and volume vector for similarity matching."""
        if self.df_data is None:
            return None
            
        sub = self.df_data.filter(
            (pl.col("symbol") == symbol) & (pl.col("time") <= end_date)
        ).tail(lookback)
        
        if len(sub) < lookback:
            return None
            
        closes = sub["close"].to_numpy()
        vols = sub["volume"].to_numpy()
        
        # Min-max normalization for shape invariant matching
        c_min, c_max = np.min(closes), np.max(closes)
        c_norm = (closes - c_min) / ((c_max - c_min) + 1e-9)
        
        v_mean = np.mean(vols)
        v_norm = vols / (v_mean + 1e-9)
        v_norm = np.clip(v_norm, 0.0, 3.0) / 3.0
        
        # Combine price (70% weight) and volume (30% weight)
        fingerprint = np.concatenate([c_norm * 0.7, v_norm * 0.3])
        return fingerprint

    def match_pattern(self, symbol: str, target_date: str = None) -> dict:
        """Compares current stock pattern against golden templates."""
        symbol = symbol.strip().upper()
        if self.df_data is None:
            return {"status": "error", "message": "Chưa có dữ liệu Parquet"}
            
        if not target_date:
            target_date = self.df_data.filter(pl.col("symbol") == symbol)["time"].max()
            
        current_fp = self.extract_fingerprint(symbol, target_date, lookback=25)
        if current_fp is None:
            return {
                "status": "warning",
                "message": f"Không đủ dữ liệu lịch sử (ít nhất 25 phiên) cho mã {symbol} tại ngày {target_date}"
            }
            
        best_match = None
        best_score = -1.0
        
        for g in self.golden_patterns:
            g_sym = g["symbol"]
            g_end = g["end_date"]
            g_fp = self.extract_fingerprint(g_sym, g_end, lookback=25)
            
            if g_fp is not None:
                # Cosine Similarity
                dot_prod = np.dot(current_fp, g_fp)
                norm_a = np.linalg.norm(current_fp)
                norm_b = np.linalg.norm(g_fp)
                similarity = (dot_prod / (norm_a * norm_b + 1e-9)) * 100.0
                
                if similarity > best_score:
                    best_score = similarity
                    best_match = g
                    
        # Check current tier status from parquet
        curr_row = self.df_data.filter(
            (pl.col("symbol") == symbol) & (pl.col("time") == target_date)
        )
        current_phase = "Theo dõi tích lũy"
        if not curr_row.is_empty():
            r = curr_row.to_dicts()[0]
            if r.get("cand_t3_flag") == 1:
                current_phase = "Điểm Pivot / Nổ Vượt Đỉnh (Tầng 3)"
            elif r.get("cand_t2_flag") == 1:
                current_phase = "Điểm Đẩy Nền Pocket Pivot (Tầng 2)"
            elif r.get("cand_t1_flag") == 1:
                current_phase = "Điểm Mua Cược Kiệt Cung (Tầng 1)"
                
        return {
            "status": "success",
            "symbol": symbol,
            "target_date": target_date,
            "current_phase": current_phase,
            "best_match_pattern": best_match["name"] if best_match else "Mẫu hình tích lũy chung",
            "reference_stock": f"{best_match['symbol']} ({best_match['start_date']} -> {best_match['end_date']})" if best_match else "N/A",
            "similarity_score_pct": round(float(best_score), 1) if best_match else 0.0,
            "historical_result": best_match["result"] if best_match else "N/A",
            "pattern_note": best_match["note"] if best_match else "",
            "image_file": best_match.get("image_file", "") if best_match else "",
            "image_indicators": best_match.get("image_indicators", "") if best_match else ""
        }

if __name__ == "__main__":
    matcher = VSAPatternMatcher()
    print("Tổng số ca mẫu vàng nạp vào:", len(matcher.golden_patterns))
    # Test on a real case
    test_res = matcher.match_pattern("DGC", "2021-08-11")
    print("\nTest so khớp DGC ngày 11/08/2021:")
    for k, v in test_res.items():
        print(f"  {k}: {v}")
