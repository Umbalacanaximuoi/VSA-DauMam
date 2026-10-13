"""
vsa_mobile_service.py
Dịch vụ cung cấp dữ liệu đánh giá 4 Điểm Số (VSA - BDI - BMS - No2) và 4 Trạng thái Khuyến nghị
phục vụ giao diện Điện Thoại & GitHub Web App.
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluator
import bdi_engine
import bdi_momentum

try:
    from data_pipeline.no2_engine import detect_no2_in_df, get_no2_current_candidates
except ImportError:
    detect_no2_in_df = None
    get_no2_current_candidates = None

def evaluate_stock_mobile(symbol: str, target_date_str: str = None) -> dict:
    sym = symbol.strip().upper()
    
    # 1. Tải dữ liệu cổ phiếu
    df = evaluator.get_prepared_stock_df(sym, target_date_str=target_date_str, force_reload=True)
    if df is None or df.empty or len(df) < 20:
        return {
            "status": "error",
            "message": f"Không tìm thấy dữ liệu giao dịch cho mã cổ phiếu {sym}."
        }
        
    latest_row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) > 1 else latest_row
    
    close_p = float(latest_row['close'])
    prev_close = float(prev_row['close'])
    chg_pct = ((close_p - prev_close) / (prev_close + 1e-9)) * 100.0
    vol = int(latest_row['volume'])
    avg_v10 = float(latest_row.get('avg_vol10', vol))
    avg_v20 = float(latest_row.get('avg_vol20', vol))
    vol_r10 = vol / (avg_v10 + 1e-9)
    vol_r20 = vol / (avg_v20 + 1e-9)
    trade_date = str(latest_row['time'])[:10] if 'time' in latest_row else datetime.now().strftime("%Y-%m-%d")

    # 2. CHẤM ĐIỂM VSA (Thang điểm 100)
    vsa_eval = evaluator.evaluate_stock_from_df(df, sym, target_date_str=target_date_str)
    vsa_score = float(vsa_eval.get('score', 50.0))
    vsa_rating = vsa_eval.get('rating', 'Trung Bình')
    
    # Diễn giải hành vi VSA
    if vsa_score >= 75:
        vsa_behavior = "Bên Mua kiểm soát hoàn toàn thế trận. Dòng tiền lớn hấp thụ mạnh mẽ nguồn cung trôi nổi."
        vsa_color = "emerald"
    elif vsa_score >= 50:
        vsa_behavior = "Trạng thái cân bằng tích lũy. Cung cầu giằng co trong biên độ kiểm soát của tổ chức."
        vsa_color = "amber"
    else:
        vsa_behavior = "Áp lực cung chiếm ưu thế hoặc cổ phiếu đang trong pha rũ bỏ chưa kiệt vol."
        vsa_color = "rose"

    # 3. CHẤM ĐIỂM BDI (VSA Ông Bình Design Index - Thang điểm 100)
    bdi_eval = bdi_engine.score_bdi_stock(sym, target_date_str=target_date_str)
    bdi_score = int(bdi_eval.get('bdi_score', 50))
    bdi_rec = bdi_eval.get('recommendation', 'Thăm dò')
    point_code = bdi_eval.get('point_code', 'NONE')
    is_breakout = bdi_eval.get('is_breakout', False)
    is_pivot = bdi_eval.get('is_pivot', False)
    is_cuoc = bdi_eval.get('is_cuoc', False)
    is_vol_surge = bdi_eval.get('is_volume_surge', False)

    # 4. CHẤM ĐIỂM BMS (Xung Lực BDI - Thang điểm 100)
    bms_eval = bdi_momentum.get_latest_bms_momentum(sym, df=df, force_reload=False)
    bms_score = float(bms_eval.get('bms_score', 50.0))
    bms_tier = bms_eval.get('tier', 'C')
    bms_badge = bms_eval.get('badge', 'XUNG LỰC TRUNG BÌNH')
    sub_scores = bms_eval.get("sub_scores", {"rs": 12.5, "vdu": 12.5, "vcp": 10.0, "smd": 7.5, "pa": 7.5})

    # 5. CHIẾN LƯỢC SĂN SIÊU CỔ NỀN SỐ 2 (STRATEGY No2)
    no2_data = {
        "score": 0.0,
        "is_no2": False,
        "action_code": "WATCH",
        "action_status": "Chưa hình thành cấu trúc Nền 2",
        "status_label": "Chưa đạt Nền 2",
        "color": "slate",
        "stage1_gain": 0.0,
        "base2_duration": 0,
        "base2_depth": 0.0,
        "pillars": {},
        "capital_plan": {}
    }
    try:
        if detect_no2_in_df:
            no2_eval = detect_no2_in_df(df)
            if no2_eval and no2_eval.get("no2_score") is not None:
                n_score = float(no2_eval.get("no2_score", 0.0))
                is_n2 = bool(no2_eval.get("is_no2", False))
                act_code = no2_eval.get("action_code", "WATCH")
                act_status = no2_eval.get("action_status", "Đang theo dõi tích lũy")
                
                if act_code == "C1":
                    status_lbl = "🎯 Cược C1: Kiệt Cung Nền 2"
                    n_col = "amber"
                elif act_code == "P1":
                    status_lbl = "🌱 Kích Hoạt P1: Pocket Nền 2"
                    n_col = "sky"
                elif act_code == "B1":
                    status_lbl = "🚀 Bứt Nền B1: Siêu Sóng Nhịp 2"
                    n_col = "emerald"
                else:
                    status_lbl = "Đang Tích Lũy Nền 2" if is_n2 or n_score >= 60 else "Chưa Đạt Nền 2"
                    n_col = "purple" if is_n2 else "slate"
                    
                no2_data = {
                    "score": round(n_score, 1),
                    "is_no2": is_n2,
                    "action_code": act_code,
                    "action_status": act_status,
                    "status_label": status_lbl,
                    "color": n_col,
                    "stage1_gain": round(float(no2_eval.get("stage1_gain_pct", 0.0)), 1),
                    "base2_duration": int(no2_eval.get("base2_duration_days", 0)),
                    "base2_depth": round(float(no2_eval.get("base2_depth_pct", 0.0)), 1),
                    "pillars": no2_eval.get("pillars", {}),
                    "capital_plan": no2_eval.get("capital_plan", {})
                }
    except Exception:
        pass

    # 6. KHUYẾN NGHỊ THỰC CHIẾN (4 TRẠNG THÁI HÀNH VI: Cược C, Pivot P, Breakout B, Quan sát)
    low_price = float(latest_row['low'])
    stop_loss = round(low_price * 0.985, 2)
    risk_pct = round(((close_p - stop_loss) / (close_p + 1e-9)) * 100.0, 1)

    if is_vol_surge or is_breakout or point_code == "B1":
        rec_type = "B"
        rec_label = "Breakout B"
        rec_badge = "🚀 BREAKOUT B — XÁC NHẬN BỨT PHÁ"
        rec_headline = "Chuyến tàu cuối cùng cho vị thế chuẩn"
        rec_action = "Xác nhận bứt phá Pha E khỏi vùng tích lũy. Đủ điều kiện hoàn tất 100% vị thế tiền mặt theo kế hoạch. Tuyệt đối không mua đuổi sau phiên này."
        rec_color = "emerald"
        rec_step = "Tầng 3 / 4: Bứt Nền Dứt Khoát"
    elif is_pivot or point_code == "P1":
        rec_type = "P"
        rec_label = "Pivot P"
        rec_badge = "🌱 PIVOT P — ĐẨY NỀN POCKET PIVOT"
        rec_headline = "Lò xo bung chốt – Bạn nên có mặt!"
        rec_action = "Phát súng hiệu dòng tiền tổ chức nhập cuộc chớm nhú từ nền giá. Đạt điều kiện mở vị thế đón đầu hoặc gia tăng khi có đệm lãi."
        rec_color = "sky"
    elif is_cuoc or point_code == "C1":
        rec_type = "C"
        rec_label = "Cược C"
        rec_badge = "🎯 CƯỢC C — KIỆT CUNG NỀN SIẾT"
        rec_headline = "Cân nhắc đưa vào danh mục theo dõi"
        rec_action = "Vùng tích lũy cạn kiệt nguồn cung, rủi ro sụt giảm thấp nhất. Đạt tiêu chuẩn thử nghiệm vị thế thăm dò 1/8 tại điểm tựa giá vốn."
        rec_color = "amber"
        rec_step = "Tầng 1 / 4: Thăm Dò Nền Giá"
    elif point_code == "AFTER_BO":
        rec_type = "OBSERVE"
        rec_label = "Chờ Nền 2"
        rec_badge = "⏳ RETEST SAU NỔ — CHỜ SETUP NỀN MỚI"
        rec_headline = "Vừa bùng nổ, đang hấp thụ lực chốt lời"
        rec_action = "Cổ phiếu vừa có phiên nổ khối lượng lớn. Theo chuẩn VSA, cần chờ tối thiểu 1 tuần (>= 5 phiên) để hoàn tất cấu trúc Nền 2 (rũ bỏ & kiệt cung) trước khi mở vị thế mới."
        rec_color = "purple"
        rec_step = "Quan Sát Tạo Nền Mới"
    elif no2_data["is_no2"] and no2_data["action_code"] in ("C1", "P1"):
        # Ưu tiên kích hoạt theo Chiến Lược No2 khi cổ phiếu đang nén nền 2
        if no2_data["action_code"] == "P1":
            rec_type = "P"
            rec_label = "Pivot P1 (No2)"
            rec_badge = "🌱 CHIẾN LƯỢC No2 — POCKET NỀN 2 (P1)"
            rec_headline = "Điểm giải phóng năng lượng – Nhập cuộc chân sóng nhịp 2"
            rec_action = f"Xuất hiện Pocket Pivot nhú từ Nền 2 (nền siết {no2_data['base2_duration']} phiên, chỉnh nhẹ {no2_data['base2_depth']}%). Đạt chuẩn gia tăng vị thế đón đầu nhịp tăng chính."
            rec_color = "sky"
            rec_step = "Chiến Lược No2: Giải Phóng Năng Lượng P1"
        else:
            rec_type = "C"
            rec_label = "Cược C1 (No2)"
            rec_badge = "🏆 CHIẾN LƯỢC No2 — SĂN NỀN 2 KIỆT CUNG (C1)"
            rec_headline = "Nền số 2 cạn cung tuyệt đối – Chuẩn bị bung lò xo"
            rec_action = f"Cổ phiếu đã tăng nhịp 1 (+{no2_data['stage1_gain']}%) và đang siết Nền 2 ({no2_data['base2_duration']} phiên). Đạt tiêu chuẩn mở vị thế cược C1 chủ động trong nền giá."
            rec_color = "amber"
            rec_step = "Chiến Lược No2: Thăm Dò Kiệt Cung C1"
    else:
        rec_type = "OBSERVE"
        rec_label = "Quan sát"
        rec_badge = "👁️ QUAN SÁT — CHỜ DÒNG TIỀN XÁC NHẬN"
        rec_headline = "Chưa xuất hiện điểm xác nhận – Kiên nhẫn bảo toàn vốn"
        rec_action = "Cổ phiếu chưa hội tụ đủ độ nén lò xo hoặc đang trong nhịp phân hóa. Giữ kỷ luật kiên nhẫn, bảo toàn sức mua chờ giờ G."
        rec_color = "slate"
        rec_step = "Quản Trị Rủi Ro Chủ Động"

    # 7. BÓC TÁCH 5 THƯỚC ĐO HÀNH VI (100% không lộ RSI, MACD, MA...)
    rs_sub = sub_scores.get('rs', 15)
    vdu_sub = sub_scores.get('vdu', 15)
    vcp_sub = sub_scores.get('vcp', 10)
    smd_sub = sub_scores.get('smd', 8)
    pa_sub = sub_scores.get('pa', 8)

    behavior_cards = [
        {
            "name": "1. Sức Mạnh Tương Quan (RS)",
            "score": f"{rs_sub:.1f}/25đ",
            "desc": "Kháng cự sụt giảm vượt trội so với thị trường chung" if rs_sub >= 16 else "Vận động đồng pha hoặc giữ giá cùng nhịp chỉ số",
            "status": "Tốt" if rs_sub >= 16 else "Trung bình"
        },
        {
            "name": "2. Động Lực Kiệt Cung (VDU)",
            "score": f"{vdu_sub:.1f}/25đ",
            "desc": "Nguồn cung trôi nổi kiệt quệ hoàn toàn (No Supply Bar)" if vdu_sub >= 16 else "Lực bán đã giảm dần nhưng còn thăm dò cung cầu",
            "status": "Cạn cung" if vdu_sub >= 16 else "Thăm dò"
        },
        {
            "name": "3. Độ Nén Cấu Trúc (VCP)",
            "score": f"{vcp_sub:.1f}/20đ",
            "desc": "Lò xo nén cực đại, biên độ dao động siết chặt tại điểm nghẽn" if vcp_sub >= 13 else "Biên độ giá đang trong quá trình thu hẹp dần",
            "status": "Nén chặt" if vcp_sub >= 13 else "Đang siết"
        },
        {
            "name": "4. Dòng Tiền Ngầm (SMD)",
            "score": f"{smd_sub:.1f}/15đ",
            "desc": "Dấu chân Nhà tạo lập âm thầm thu gom ròng liên tục" if smd_sub >= 10 else "Dòng tiền lớn giữ nhịp thăm dò, chưa đẩy dứt khoát",
            "status": "Gom lén" if smd_sub >= 10 else "Cân bằng"
        },
        {
            "name": "5. Vị Thế Chốt Chặn (PA)",
            "score": f"{pa_sub:.1f}/15đ",
            "desc": "Bảo vệ thành công Điểm Tựa Giá Vốn (LPS), sẵn sàng bứt phá" if pa_sub >= 10 else "Đang kiểm định lại ngưỡng đỡ giá của tổ chức",
            "status": "Đạt chuẩn" if pa_sub >= 10 else "Kiểm định"
        }
    ]

    return {
        "status": "success",
        "symbol": sym,
        "date": trade_date,
        "close": close_p,
        "prev_close": prev_close,
        "chg_pct": round(chg_pct, 2),
        "volume": vol,
        "vol_r10": round(vol_r10, 2),
        "vol_r20": round(vol_r20, 2),
        "scores": {
            "vsa": {
                "score": round(vsa_score, 1),
                "rating": vsa_rating,
                "behavior": vsa_behavior,
                "color": vsa_color
            },
            "bdi": {
                "score": bdi_score,
                "rating": bdi_rec,
                "behavior": "Cấu trúc tích lũy đạt chuẩn VSA 8 tiêu chí" if bdi_score >= 65 else "Cấu trúc đang hoàn thiện, cần thêm thời gian tích lũy",
                "color": "emerald" if bdi_score >= 65 else ("amber" if bdi_score >= 50 else "rose")
            },
            "bms": {
                "score": round(bms_score, 1),
                "tier": bms_tier,
                "badge": bms_badge,
                "behavior": "Lò xo nén cực đại, đạt trạng thái giải phóng năng lượng" if bms_score >= 80 else ("Đang tích lũy xung lực khá" if bms_score >= 70 else "Xung lực trung bình"),
                "color": "purple" if bms_score >= 80 else ("emerald" if bms_score >= 70 else "amber")
            },
            "no2": no2_data
        },
        "recommendation": {
            "type": rec_type,
            "label": rec_label,
            "badge": rec_badge,
            "headline": rec_headline,
            "action": rec_action,
            "color": rec_color,
            "step": rec_step,
            "stop_loss": stop_loss,
            "risk_pct": risk_pct
        },
        "behavior_breakdown": behavior_cards
    }

def get_mobile_no2_radar(min_score: float = 55.0, limit: int = 25) -> list:
    """Lấy danh sách top cổ phiếu Nền Số 2 định dạng nhẹ tối ưu cho màn hình di động."""
    try:
        if get_no2_current_candidates:
            raw_list = get_no2_current_candidates(min_score=min_score)
            if raw_list:
                result = []
                for item in raw_list[:limit]:
                    result.append({
                        "symbol": item.get("symbol", ""),
                        "no2_score": round(float(item.get("no2_score", 0.0)), 1),
                        "bms_score": round(float(item.get("bms_score", 0.0)), 1),
                        "bms_tier": item.get("bms_tier", "B"),
                        "action_code": item.get("action_code", "WATCH"),
                        "action_status": item.get("action_status", "Nền 2"),
                        "close": item.get("close", 0.0),
                        "stage1_gain": item.get("stage1_gain_pct", 0.0),
                        "base2_duration": item.get("base2_duration_days", 0),
                        "base2_depth": item.get("base2_depth_pct", 0.0)
                    })
                return result
    except Exception:
        pass
    return []

if __name__ == "__main__":
    import json
    res = evaluate_stock_mobile("SBG")
    print(json.dumps(res, ensure_ascii=False, indent=2))
