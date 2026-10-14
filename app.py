import os
import sys
import json
import logging
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Correctly determine base directory whether running from source or frozen PyInstaller .exe
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
    MEI_DIR = getattr(sys, '_MEIPASS', APP_DIR)
    BASE_DIR = APP_DIR if os.path.exists(os.path.join(APP_DIR, "static")) else MEI_DIR
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STATIC_DIR = os.path.join(BASE_DIR, "static")
if not os.path.exists(STATIC_DIR) and getattr(sys, 'frozen', False):
    STATIC_DIR = os.path.join(getattr(sys, '_MEIPASS', BASE_DIR), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

app = FastAPI(title="VSA Đậu Mầm Pro - Hệ Thống VSA & Sóng Ngành", version="2.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

CHART_IMAGE_DIR = os.path.join(BASE_DIR, "tai_lieu_hoc_may_vsa", "03_hinh_mau_bieu_do")
if not os.path.exists(CHART_IMAGE_DIR) and getattr(sys, 'frozen', False):
    alt_charts = os.path.join(getattr(sys, '_MEIPASS', BASE_DIR), "tai_lieu_hoc_may_vsa", "03_hinh_mau_bieu_do")
    if os.path.exists(alt_charts):
        CHART_IMAGE_DIR = alt_charts
if os.path.exists(CHART_IMAGE_DIR):
    app.mount("/chart_images", StaticFiles(directory=CHART_IMAGE_DIR), name="chart_images")

import pandas as pd
import numpy as np
import time
from concurrent.futures import ThreadPoolExecutor
from license_manager import (
    verify_license_status,
    activate_license,
    reset_local_license,
    get_hardware_id,
    admin_login,
    admin_list_licenses,
    admin_create_license,
    admin_renew_license,
    admin_revoke_license,
    admin_unrevoke_license,
    admin_delete_license,
    admin_get_expiring_warnings,
    verify_admin_token
)
from evaluator import (
    evaluate_stock_from_df,
    get_prepared_stock_df,
    evaluate_sector_wave,
    SECTOR_PEERS_MAP,
    SECTOR_TIERS_CONFIG,
    SYMBOL_SECTOR_LOOKUP
)
from reasoning_engine import generate_detailed_reasoning
from vsa_mobile_service import evaluate_stock_mobile, get_mobile_no2_radar

class EvaluateRequest(BaseModel):
    symbol: str
    target_date: Optional[str] = None

class MobileEvaluateRequest(BaseModel):
    symbol: str
    target_date: Optional[str] = None

class ActivateRequest(BaseModel):
    license_key: str

class AdminLoginRequest(BaseModel):
    password: str

class AdminCreateKeyRequest(BaseModel):
    client_name: str
    days: int = 30
    bound_hwid: str = "ANY"
    plan_name: str = "VIP"
    notes: Optional[str] = ""

class AdminRenewKeyRequest(BaseModel):
    license_key: str
    extra_days: int = 30

class AdminKeyActionRequest(BaseModel):
    license_key: str

def check_is_admin(request: Request) -> bool:
    if not request:
        return False
    try:
        auth_header = request.headers.get("Authorization")
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
        elif "token" in request.query_params:
            token = request.query_params["token"]
        elif "admin_token" in request.query_params:
            token = request.query_params["admin_token"]
            
        return bool(token and verify_admin_token(token))
    except Exception:
        return False

def require_admin_auth(request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=401, detail="Khóa xác thực Quản Trị Viên không hợp lệ!")
    return True

def require_active_license(request: Request = None):
    if request and check_is_admin(request):
        return {
            "valid": True,
            "status": "ACTIVE",
            "message": "Quản Trị Viên (Toàn Quyền Hệ Thống)",
            "client": "Admin VSA Pro",
            "plan": "ADMIN_MASTER",
            "days_left": 99999,
            "is_admin": True
        }
    lic = verify_license_status()
    if not lic["valid"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "LICENSE_BLOCKED",
                "status": lic["status"],
                "message": lic["message"],
                "hwid": lic.get("hwid"),
                "days_left": 0
            }
        )
    return lic

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>VSA Đậu Mầm Pro UI is loading...</h1>")

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin():
    admin_path = os.path.join(STATIC_DIR, "admin.html")
    if os.path.exists(admin_path):
        with open(admin_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>VSA Đậu Mầm Pro Admin Portal is loading...</h1>")

@app.get("/mobile", response_class=HTMLResponse)
async def serve_mobile():
    mobile_path = os.path.join(STATIC_DIR, "mobile.html")
    if os.path.exists(mobile_path):
        with open(mobile_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>VSA Đậu Mầm Pro Mobile UI is loading...</h1>")

@app.get("/simulator", response_class=HTMLResponse)
async def serve_simulator():
    sim_path = os.path.join(STATIC_DIR, "simulator.html")
    if os.path.exists(sim_path):
        with open(sim_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>VSA Mobile Simulator is loading...</h1>")

@app.post("/api/evaluate_mobile")
async def api_evaluate_mobile(req: MobileEvaluateRequest):
    sym = req.symbol.strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="Vui lòng nhập mã cổ phiếu")
    res = evaluate_stock_mobile(sym, target_date_str=req.target_date)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", f"Không tìm thấy dữ liệu cho mã {sym}"))
    return res

@app.get("/api/mobile_no2_radar")
async def api_mobile_no2_radar(min_score: float = 55.0):
    try:
        data = get_mobile_no2_radar(min_score=min_score)
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "data": []}


@app.get("/api/license/status")
async def get_license_status(request: Request):
    if check_is_admin(request):
        return {
            "valid": True,
            "status": "ACTIVE",
            "message": "👑 Quản Trị Viên (Toàn Quyền Hệ Thống)",
            "client": "Admin VSA Pro",
            "plan": "ADMIN_MASTER",
            "days_left": 99999,
            "is_admin": True,
            "hwid": get_hardware_id()
        }
    return verify_license_status()

@app.post("/api/license/activate")
async def activate_user_license(req: ActivateRequest):
    return activate_license(req.license_key)

@app.post("/api/license/reset")
async def api_reset_license():
    return reset_local_license()

@app.get("/api/license/hwid")
async def get_machine_hwid():
    return {"hwid": get_hardware_id()}

# ==================== ADMIN CLOUD MANAGEMENT APIS ====================

@app.post("/api/admin/login")
async def api_admin_login(req: AdminLoginRequest):
    res = admin_login(req.password)
    if not res["success"]:
        raise HTTPException(status_code=401, detail=res["message"])
    return res

@app.get("/api/admin/licenses")
async def api_admin_list_licenses(request: Request):
    require_admin_auth(request)
    return admin_list_licenses()

@app.post("/api/admin/licenses/create")
async def api_admin_create_license(req: AdminCreateKeyRequest, request: Request):
    require_admin_auth(request)
    res = admin_create_license(
        client_name=req.client_name,
        days=req.days,
        bound_hwid=req.bound_hwid,
        plan_name=req.plan_name,
        notes=req.notes or ""
    )
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.post("/api/admin/licenses/renew")
async def api_admin_renew_license(req: AdminRenewKeyRequest, request: Request):
    require_admin_auth(request)
    res = admin_renew_license(req.license_key, req.extra_days)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.post("/api/admin/licenses/revoke")
async def api_admin_revoke_license(req: AdminKeyActionRequest, request: Request):
    require_admin_auth(request)
    res = admin_revoke_license(req.license_key)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.post("/api/admin/licenses/unrevoke")
async def api_admin_unrevoke_license(req: AdminKeyActionRequest, request: Request):
    require_admin_auth(request)
    res = admin_unrevoke_license(req.license_key)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.post("/api/admin/licenses/delete")
async def api_admin_delete_license(req: AdminKeyActionRequest, request: Request):
    require_admin_auth(request)
    res = admin_delete_license(req.license_key)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.get("/api/admin/warnings")
async def api_admin_warnings(request: Request, days: int = 7):
    require_admin_auth(request)
    return admin_get_expiring_warnings(threshold_days=days)

@app.post("/api/evaluate")
async def evaluate_stock(req: EvaluateRequest, request: Request):
    lic = require_active_license(request)
    sym = req.symbol.strip().upper()
    df = get_prepared_stock_df(sym, target_date_str=req.target_date)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dữ liệu cho mã {sym}")
        
    eval_res = evaluate_stock_from_df(df, sym, target_date_str=req.target_date)
    ai_reasoning = generate_detailed_reasoning(eval_res)
    sector_id = SYMBOL_SECTOR_LOOKUP.get(sym, "NGAN_HANG")
    eval_res["sector_id"] = sector_id

    # 1. Machine Learning Inference & Pattern Matching
    target_d = req.target_date or (str(df.iloc[-1]['time'])[:10] if 'time' in df.columns else None)
    ml_pred = None
    pat_res = None
    try:
        from data_pipeline.ml_inference import VSAMLInferenceEngine
        from data_pipeline.pattern_matcher import VSAPatternMatcher
        ml_engine = VSAMLInferenceEngine()
        ml_pred = ml_engine.predict_symbol_date(sym, target_d, live_df=df)
        
        pat_matcher = VSAPatternMatcher()
        pat_res = pat_matcher.match_pattern(sym, target_d)
    except Exception as e:
        logging.error(f"Lỗi ML / Pattern matcher: {e}")

    # 2. Quy Tắc Kỷ Luật Zero-Loss: Khoảng cách tới đáy nền kiệt cung
    zero_loss_metrics = None
    try:
        cur_row = df.iloc[-1]
        cur_close = float(cur_row['close'])
        lookback_df = df.iloc[-15:]
        min_close_base = float(lookback_df['close'].min())
        dist_to_base_pct = float((cur_close - min_close_base) / (cur_close + 1e-9) * 100)
        zero_loss_safe = bool(dist_to_base_pct <= 2.5)
        
        zero_loss_metrics = {
            "cur_close": round(cur_close, 2),
            "min_close_base": round(min_close_base, 2),
            "dist_to_base_pct": round(dist_to_base_pct, 2),
            "is_safe": zero_loss_safe,
            "rule_desc": f"Đáy nền kiệt cung: {min_close_base:,.2f} | Khoảng cách: {dist_to_base_pct:+.2f}%"
        }
    except Exception:
        zero_loss_metrics = None

    # 3. Quy Tắc Kỷ Luật Zero-Đỉnh: Kiểm tra 50% thân nến nổ trong 5 phiên
    zero_dinh_metrics = None
    try:
        recent_window = df.iloc[-5:]
        break_cand = None
        for i in range(len(recent_window) - 1, -1, -1):
            rw = recent_window.iloc[i]
            prev_rw = df.iloc[len(df) - 5 + i - 1] if (len(df) - 5 + i - 1) >= 0 else rw
            chg = (float(rw['close']) - float(prev_rw['close'])) / (float(prev_rw['close']) + 1e-9) * 100
            vol_r = float(rw['volume']) / (float(rw['avg_vol10']) + 1e-9) if 'avg_vol10' in rw else 1.0
            if chg >= 2.5 and vol_r >= 1.1:
                break_cand = rw
                break
                
        if break_cand is not None:
            b_open = float(break_cand['open'])
            b_close = float(break_cand['close'])
            half_body = (b_open + b_close) / 2.0
            cur_close = float(df.iloc[-1]['close'])
            is_above_half = cur_close >= half_body
            zero_dinh_metrics = {
                "has_recent_breakout": True,
                "break_date": str(break_cand['time'])[:10] if 'time' in break_cand else "N/A",
                "break_close": round(b_close, 2),
                "half_body_level": round(half_body, 2),
                "is_above_half": is_above_half,
                "status_text": "GIỮ VỮNG >50% THÂN NẾN (Chuẩn Zero Đỉnh)" if is_above_half else "⚠️ CẢNH BÁO GÃY 50% THÂN NẾN (Nguy cơ Bulltrap)"
            }
        else:
            zero_dinh_metrics = {
                "has_recent_breakout": False,
                "status_text": "Chưa có phiên nổ gần nhất trong 5 phiên qua"
            }
    except Exception:
        zero_dinh_metrics = None
    
    return {
        "status": "success",
        "license_info": {
            "client": lic.get("client"),
            "plan": lic.get("plan"),
            "days_left": lic.get("days_left"),
            "is_admin": lic.get("is_admin", False)
        },
        "data": eval_res,
        "ai_reasoning": ai_reasoning,
        "ml_prediction": ml_pred,
        "pattern_match": pat_res,
        "zero_loss_metrics": zero_loss_metrics,
        "zero_dinh_metrics": zero_dinh_metrics
    }

@app.get("/api/sector_wave/{sector_id}")
async def get_sector_wave(sector_id: str, request: Request, target_date: Optional[str] = None):
    lic = require_active_license(request)
    res = evaluate_sector_wave(sector_id, target_date_str=target_date)
    return {
        "status": "success",
        "license_info": {
            "client": lic.get("client"),
            "days_left": lic.get("days_left"),
            "is_admin": lic.get("is_admin", False)
        },
        "data": res
    }

_SCAN_3_TIERS_CACHE = {}

@app.get("/api/scan_3_tiers")
async def scan_3_tiers(request: Request, target_date: Optional[str] = None):
    lic = require_active_license(request)
    cache_key = target_date or "latest"
    now_ts = time.time()
    if cache_key in _SCAN_3_TIERS_CACHE:
        cached_time, cached_res = _SCAN_3_TIERS_CACHE[cache_key]
        if now_ts - cached_time < 60:
            return cached_res

    universe = [
        "VCB", "BID", "CTG", "TCB", "MBB", "VPB", "ACB", "STB", "HDB", "SHB", "TPB", "SSB",
        "SSI", "VND", "VCI", "HCM", "SHS", "MBS", "VIX", "FTS", "BSI", "CTS", "AGR",
        "VHM", "VIC", "VRE", "NVL", "PDR", "DIG", "DXG", "KDH", "NLG", "KBC", "VPI", "HDC", "CEO", "TCH",
        "GAS", "PVD", "PVS", "BSR", "PLX", "PVT", "PVC", "PVB", "OIL",
        "MWG", "FRT", "PNJ", "DGW", "MSN", "PET", "VNM", "SAB", "DBC", "BAF",
        "HPG", "HSG", "NKG", "VGS", "TLH", "KSB", "BMP",
        "DGC", "CSV", "DPM", "DCM", "BFC", "LAS", "DDV", "GVR",
        "GMD", "HAH", "VSC", "VOS", "VIP", "VTO"
    ]

    # Tải trước bảng giá trực tuyến batch 1 lần duy nhất cho toàn bộ universe
    if target_date is None:
        try:
            from evaluator import preload_live_price_board
            preload_live_price_board(universe)
        except (Exception, SystemExit, BaseException):
            pass

    def scan_single(sym):
        try:
            df = get_prepared_stock_df(sym, target_date_str=target_date)
            if df is None or df.empty or len(df) < 20:
                return None
                
            eval_res = evaluate_stock_from_df(df, sym, target_date_str=target_date)
            row = df.iloc[-1]
            idx_curr = len(df) - 1
            prev_row = df.iloc[-2]
            
            close = float(row['close'])
            prev_close = float(prev_row['close'])
            chg_pct = float((close - prev_close) / (prev_close + 1e-9) * 100)
            avg_vol10 = float(row['avg_vol10']) if 'avg_vol10' in row else 1.0
            vol_r10 = float(row['volume'] / (avg_vol10 + 1e-9))
            candle_len = float(row['high'] - row['low'])
            close_high_ratio = float((close - float(row['low'])) / (candle_len + 1e-9)) if candle_len > 0 else 1.0
            upper_wick_ratio = float((float(row['high']) - close) / (candle_len + 1e-9)) if candle_len > 0 else 0.0
            is_upbar = bool(close > prev_close)
            ma50_val = float(row['ma50']) if 'ma50' in row else 0.0
            ma20_val = float(row['ma20']) if 'ma20' in row else 0.0
            above_ma50 = bool(close >= ma50_val)
            above_ma20 = bool(close >= ma20_val)
            score = float(eval_res.get("score", 0))
            rec_desc = str(eval_res.get("recommendation_desc", ""))
            rsi_val = float(row['rsi']) if 'rsi' in row and pd.notna(row['rsi']) else 50.0
            
            had_base = False
            for lb in range(max(0, idx_curr - 4), idx_curr):
                eval_lb = evaluate_stock_from_df(df, sym, target_date_str=str(df.iloc[lb]['time']))
                desc_lb = str(eval_lb.get("recommendation_desc", ""))
                lb_row = df.iloc[lb]
                lb_vol = float(lb_row['volume'])
                lb_avg_vol10 = float(lb_row['avg_vol10']) if 'avg_vol10' in lb_row else 1.0
                if "Điểm Cược" in desc_lb or "Điểm BU" in desc_lb or lb_vol < 0.85 * lb_avg_vol10:
                    had_base = True
                    break
                    
            item = {
                "symbol": str(sym),
                "close": round(close, 2),
                "chg_pct": round(chg_pct, 2),
                "vol_r10": round(vol_r10, 2),
                "score": round(score, 1),
                "rsi": round(rsi_val, 1),
                "above_ma50": above_ma50,
                "above_ma20": above_ma20,
                "desc": rec_desc
            }
            
            tier = None
            if "Điểm Nổ" in rec_desc or "Breakout" in rec_desc or "Điểm Pivot" in rec_desc or "Điểm BU" in rec_desc or score >= 70:
                tier = "tier3"
            elif (vol_r10 <= 1.5 and chg_pct > 0 and score >= 45) or "Pocket" in rec_desc or (is_upbar and close_high_ratio >= 0.65 and vol_r10 <= 1.3):
                tier = "tier2"
            else:
                from bdi_engine import check_new_base_after_breakout
                is_base_valid, _, base_meta = check_new_base_after_breakout(df, idx_curr)
                if base_meta.get("base_type") == "BREAKOUT_RECENT":
                    tier = None # Vừa nổ xong < 5 phiên, chưa setup nền mới -> Không xếp vào Điểm Cược
                elif "Điểm Cược" in rec_desc or is_base_valid:
                    tier = "tier1"
                elif (vol_r10 < 0.90 and abs(chg_pct) <= 2.0 and score >= 45 and is_base_valid):
                    tier = "tier1"
                
            return (tier, item)
        except Exception:
            return None
            
    t1_cuoc = []
    t2_pocket = []
    t3_pivot = []
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(scan_single, universe))
        
    for res in results:
        if res is not None:
            tier, item = res
            if tier == "tier1":
                t1_cuoc.append(item)
            elif tier == "tier2":
                t2_pocket.append(item)
            elif tier == "tier3":
                t3_pivot.append(item)
                
    t1_cuoc.sort(key=lambda x: x['score'], reverse=True)
    t2_pocket.sort(key=lambda x: x['score'], reverse=True)
    t3_pivot.sort(key=lambda x: x['score'], reverse=True)
    
    # Chấm điểm Machine Learning cho các ứng viên nổi bật
    ml_picks = []
    try:
        from data_pipeline.ml_inference import VSAMLInferenceEngine
        ml_eng = VSAMLInferenceEngine()
        all_candidates = t1_cuoc + t2_pocket + t3_pivot
        
        def score_candidate_ml(item):
            try:
                pred = ml_eng.predict_symbol_date(item["symbol"], target_date)
                if pred.get("status") != "error":
                    p1 = pred["tier1_cuoc"]["probability_pct"]
                    p2 = pred["tier2_pocket"]["probability_pct"]
                    p3 = pred["tier3_pivot"]["probability_pct"]
                    max_p = max(p1, p2, p3)
                    item["ml_prob"] = round(max_p, 1)
                    item["ml_t1"] = round(p1, 1)
                    item["ml_t2"] = round(p2, 1)
                    item["ml_t3"] = round(p3, 1)
                    return item if max_p >= 55.0 else None
                else:
                    item["ml_prob"] = 50.0
                    return None
            except Exception:
                item["ml_prob"] = 50.0
                return None

        # Dùng đa luồng chấm điểm ML song song siêu tốc
        with ThreadPoolExecutor(max_workers=6) as ml_executor:
            ml_results = list(ml_executor.map(score_candidate_ml, all_candidates))
            ml_picks = [it for it in ml_results if it is not None]

        ml_picks.sort(key=lambda x: x.get("ml_prob", 0), reverse=True)
    except Exception as e:
        logging.error(f"Lỗi chấm điểm ML trong scan: {e}")
        ml_picks = []

    # Lấy các ứng viên Chiến Lược No2 (Nền Số 2 trên cao)
    no2_candidates = []
    try:
        from data_pipeline.no2_engine import get_no2_current_candidates
        no2_candidates = get_no2_current_candidates(min_score=65.0, target_date=target_date)
    except Exception as e:
        logging.error(f"Lỗi lấy No2 candidates trong scan: {e}")

    resp_payload = {
        "status": "success",
        "license_info": {"client": lic.get("client"), "days_left": lic.get("days_left")},
        "data": {
            "tier1_cuoc": t1_cuoc,
            "tier2_pocket": t2_pocket,
            "tier3_pivot": t3_pivot,
            "ml_picks": ml_picks,
            "no2_candidates": no2_candidates
        }
    }
    _SCAN_3_TIERS_CACHE[cache_key] = (now_ts, resp_payload)
    return resp_payload

# ------------------------------------------------------------------------------
# RADAR SIÊU CỔ PHIẾU (SUPER STOCK AI PREDICTIVE ENGINE)
# ------------------------------------------------------------------------------
from data_pipeline.super_stock_engine import get_super_stock_engine

@app.get("/api/super_stock_radar")
async def api_super_stock_radar(min_score: float = 55.0, target_date: Optional[str] = None, request: Request = None):
    lic = require_active_license(request)
    try:
        engine = get_super_stock_engine()
        results = engine.scan_radar(target_date_str=target_date, min_score=min_score)
        return {
            "status": "success",
            "license_info": {"client": lic.get("client"), "days_left": lic.get("days_left")},
            "count": len(results),
            "data": results
        }
    except Exception as e:
        logging.error(f"Error in api_super_stock_radar: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/super_stock_detail")
async def api_super_stock_detail(symbol: str, target_date: Optional[str] = None, request: Request = None):
    lic = require_active_license(request)
    try:
        engine = get_super_stock_engine()
        res = engine.score_symbol(symbol, target_date)
        if not res:
            return JSONResponse(status_code=404, content={"status": "error", "message": f"Không tìm thấy dữ liệu cho {symbol}"})
        return {
            "status": "success",
            "license_info": {"client": lic.get("client"), "days_left": lic.get("days_left")},
            "data": res
        }
    except Exception as e:
        logging.error(f"Error in api_super_stock_detail: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# ------------------------------------------------------------------------------
# CHIẾN LƯỢC SĂN SIÊU CỔ NỀN SỐ 2 TRÊN CAO (STRATEGY No2)
# ------------------------------------------------------------------------------
from data_pipeline.no2_engine import get_no2_current_candidates, get_no2_detail_for_symbol

@app.get("/api/no2_radar")
async def api_no2_radar(min_score: float = 65.0, target_date: Optional[str] = None, request: Request = None):
    lic = require_active_license(request)
    try:
        candidates = get_no2_current_candidates(min_score=min_score, target_date=target_date)
        return {
            "status": "success",
            "license_info": {"client": lic.get("client"), "days_left": lic.get("days_left")},
            "count": len(candidates),
            "data": candidates
        }
    except Exception as e:
        logging.error(f"Error in api_no2_radar: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/no2_detail")
async def api_no2_detail(symbol: str, target_date: Optional[str] = None, request: Request = None):
    lic = require_active_license(request)
    try:
        res = get_no2_detail_for_symbol(symbol, target_date)
        if not res or res.get("status") == "error":
            return JSONResponse(status_code=404, content={"status": "error", "message": res.get("message", f"Không tìm thấy dữ liệu cho {symbol}")})
        return {
            "status": "success",
            "license_info": {"client": lic.get("client"), "days_left": lic.get("days_left")},
            "data": res
        }
    except Exception as e:
        logging.error(f"Error in api_no2_detail: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})



# ==============================================================================
# HỆ THỐNG CHẤM ĐIỂM BDI (VSA ÔNG BÌNH DESIGN INDEX) & QUẢN TRỊ RỦI RO RRBDI
# ==============================================================================
from bdi_engine import (
    score_bdi_stock,
    save_tracked_buy_position,
    quick_track_position,
    remove_tracked_position,
    evaluate_rrbdi_for_tracked_positions,
    load_watchlist_positions,
    save_watchlist_position,
    remove_watchlist_position,
    convert_watchlist_to_bought,
    evaluate_watchlist_signals
)

class BdiScoreRequest(BaseModel):
    symbol: str
    target_date: Optional[str] = None

class BdiBuyRequest(BaseModel):
    symbol: str
    buy_date: str
    buy_price: float
    shares_count: Optional[int] = 10000
    low_price: Optional[float] = None
    point_name: str
    bdi_score: int
    notes: Optional[str] = ""

class QuickTrackRequest(BaseModel):
    symbol: str
    notes: Optional[str] = "Theo dõi Bot"

class WatchlistAddRequest(BaseModel):
    symbol: str
    notes: Optional[str] = "Theo dõi điểm mua"

class WatchlistConvertRequest(BaseModel):
    symbol: str
    buy_price: float
    shares_count: Optional[int] = 10000
    buy_date: Optional[str] = None
    notes: Optional[str] = ""

@app.post("/api/bdi/score")
async def api_bdi_score(req: BdiScoreRequest, request: Request):
    lic = require_active_license(request)
    res = score_bdi_stock(req.symbol, req.target_date)
    return res

@app.post("/api/bdi/buy")
async def api_bdi_buy(req: BdiBuyRequest, request: Request):
    lic = require_active_license(request)
    saved = save_tracked_buy_position(req.dict())
    return {"status": "success", "data": saved}

@app.post("/api/bdi/quick_track")
async def api_bdi_quick_track(req: QuickTrackRequest, request: Request):
    lic = require_active_license(request)
    res = quick_track_position(req.symbol, req.notes)
    return res

@app.get("/api/bdi/tracked")
async def api_bdi_tracked(request: Request):
    lic = require_active_license(request)
    tracked = evaluate_rrbdi_for_tracked_positions()
    return {"status": "success", "data": tracked}

@app.delete("/api/bdi/tracked/{pos_id}")
async def api_bdi_delete_tracked(pos_id: str, request: Request):
    lic = require_active_license(request)
    ok = remove_tracked_position(pos_id)
    return {"status": "success" if ok else "error", "message": "Đã xóa vị thế" if ok else "Không tìm thấy vị thế"}

# ------------------------------------------------------------------------------
# WATCHLIST RADAR ENDPOINTS (DANH SÁCH THEO DÕI BẮT ĐIỂM MUA)
# ------------------------------------------------------------------------------
@app.get("/api/bdi/watchlist")
async def api_bdi_watchlist(request: Request):
    lic = require_active_license(request)
    signals = evaluate_watchlist_signals()
    return {"status": "success", "data": signals}

@app.post("/api/bdi/watchlist")
async def api_bdi_add_watchlist(req: WatchlistAddRequest, request: Request):
    lic = require_active_license(request)
    res = save_watchlist_position(req.symbol, req.notes)
    return res

@app.delete("/api/bdi/watchlist/{watch_id}")
async def api_bdi_delete_watchlist(watch_id: str, request: Request):
    lic = require_active_license(request)
    ok = remove_watchlist_position(watch_id)
    return {"status": "success" if ok else "error", "message": "Đã xóa khỏi danh sách theo dõi" if ok else "Không tìm thấy mã theo dõi"}

@app.post("/api/bdi/watchlist/convert_to_buy")
async def api_bdi_convert_to_buy(req: WatchlistConvertRequest, request: Request):
    lic = require_active_license(request)
    res = convert_watchlist_to_bought(
        symbol=req.symbol,
        buy_price=req.buy_price,
        shares_count=req.shares_count,
        buy_date=req.buy_date,
        notes=req.notes
    )
    return res

# ------------------------------------------------------------------------------
# TELEGRAM BOT CONFIG & TEST ENDPOINTS
# ------------------------------------------------------------------------------
from bot_rrbdi_service import load_telegram_config, send_telegram_alert, CONFIG_FILE

class TelegramConfigModel(BaseModel):
    bot_token: str
    chat_id: str
    enabled: bool = True

@app.get("/api/telegram/config")
async def api_get_telegram_config(request: Request):
    cfg = load_telegram_config()
    return {"status": "success", "data": cfg}

@app.post("/api/telegram/config")
async def api_save_telegram_config(cfg: TelegramConfigModel, request: Request):
    new_data = {
        "bot_token": cfg.bot_token.strip(),
        "chat_id": cfg.chat_id.strip(),
        "enabled": cfg.enabled
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    return {"status": "success", "message": "Đã lưu cấu hình Telegram thành công!"}

@app.post("/api/telegram/test")
async def api_test_telegram(request: Request):
    ok = send_telegram_alert(
        "🔔 <b>[VSA ĐẬU MẦM PRO]</b>: Kết nối Bot Telegram thành công!\n"
        "Hệ thống giám sát RRBDI đã sẵn sàng gửi cảnh báo theo đúng các khung giờ chiến lược."
    )
    return {"status": "success" if ok else "error", "message": "Gửi thành công! Kiểm tra Telegram của bạn." if ok else "Gửi thất bại. Vui lòng kiểm tra lại Token và Chat ID."}

# ------------------------------------------------------------------------------
# AMIBROKER WATCHLIST EXPORT ENDPOINT
# ------------------------------------------------------------------------------
class ExportAmiBrokerRequest(BaseModel):
    symbols: Optional[List[str]] = None
    list_name: Optional[str] = "VSA_DauMam"

@app.post("/api/export_to_amibroker")
async def api_export_to_amibroker(req: ExportAmiBrokerRequest, request: Request):
    symbols = req.symbols or []
    
    # Nếu danh sách rỗng, thử đọc từ cache kết quả quét gần nhất
    if not symbols:
        candidates_file = os.path.join(BASE_DIR, "data_mart", "current_super_stock_scan.json")
        if os.path.exists(candidates_file):
            try:
                with open(candidates_file, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                    if isinstance(cdata, list):
                        symbols = [x.get("symbol") for x in cdata if x.get("symbol")]
            except Exception:
                pass
                
    # Làm sạch & loại bỏ trùng lặp
    clean_symbols = []
    seen = set()
    for s in symbols:
        s_clean = str(s).strip().upper()
        if s_clean and s_clean not in seen:
            seen.add(s_clean)
            clean_symbols.append(s_clean)
            
    raw_name = req.list_name.strip() if req.list_name else "VSA_DauMam"
    if raw_name.endswith(".tls"):
        filename = raw_name
        raw_name = raw_name[:-4]
    else:
        filename = f"{raw_name}.tls"
        
    exported_paths = []
    
    # 1. Ghi đè vào thư mục WatchLists chính của AmiBroker (MyNewData)
    primary_dir = r"C:\Program Files (x86)\AmiBroker\MyNewData\WatchLists"
    if os.path.exists(primary_dir):
        file_path = os.path.join(primary_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            for sym in clean_symbols:
                f.write(f"{sym}\n")
        exported_paths.append(file_path)
        
        # Cập nhật index.txt để hiển thị trên cây thư mục AmiBroker
        index_file = os.path.join(primary_dir, "index.txt")
        existing_lines = []
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8", errors="ignore") as f:
                existing_lines = [l.strip() for l in f if l.strip()]
        if raw_name not in existing_lines:
            existing_lines.append(raw_name)
            with open(index_file, "w", encoding="utf-8") as f:
                for l in existing_lines:
                    f.write(f"{l}\n")
                    
    # 2. Thư mục Data thứ cấp nếu có
    sec_dir = r"C:\Program Files (x86)\AmiBroker\Data\WatchLists"
    if os.path.exists(sec_dir):
        file_path_sec = os.path.join(sec_dir, filename)
        with open(file_path_sec, "w", encoding="utf-8") as f:
            for sym in clean_symbols:
                f.write(f"{sym}\n")
        exported_paths.append(file_path_sec)
        index_sec = os.path.join(sec_dir, "index.txt")
        if os.path.exists(index_sec):
            existing_sec = []
            with open(index_sec, "r", encoding="utf-8", errors="ignore") as f:
                existing_sec = [l.strip() for l in f if l.strip()]
            if raw_name not in existing_sec:
                existing_sec.append(raw_name)
                with open(index_sec, "w", encoding="utf-8") as f:
                    for l in existing_sec:
                        f.write(f"{l}\n")
                        
    # 3. Bản sao lưu trong data_mart
    backup_dir = os.path.join(BASE_DIR, "data_mart", "amibroker_watchlists")
    os.makedirs(backup_dir, exist_ok=True)
    with open(os.path.join(backup_dir, filename), "w", encoding="utf-8") as f:
        for sym in clean_symbols:
            f.write(f"{sym}\n")
    with open(os.path.join(backup_dir, f"{raw_name}.txt"), "w", encoding="utf-8") as f:
        for sym in clean_symbols:
            f.write(f"{sym}\n")
    exported_paths.append(os.path.join(backup_dir, filename))
    
    return {
        "status": "success",
        "count": len(clean_symbols),
        "filename": filename,
        "symbols": clean_symbols,
        "exported_paths": exported_paths,
        "message": f"Đã chuyển thành công {len(clean_symbols)} mã sang AmiBroker Watchlist '{raw_name}'!"
    }
