import os
import sys
import time
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from bdi_engine import score_bdi_stock
from evaluator import SYMBOL_SECTOR_LOOKUP, SECTOR_TIERS_CONFIG, preload_live_price_board

SCAN_UNIVERSE = [
    # Ngân hàng (12)
    "VCB", "BID", "CTG", "TCB", "MBB", "VPB", "ACB", "STB", "HDB", "SHB", "TPB", "SSB",
    # Chứng khoán (11)
    "SSI", "VND", "VCI", "HCM", "SHS", "MBS", "VIX", "FTS", "BSI", "CTS", "AGR",
    # Bất động sản & KCN (14)
    "VHM", "VIC", "VRE", "NVL", "PDR", "DIG", "DXG", "KDH", "NLG", "KBC", "VPI", "HDC", "CEO", "TCH",
    # Dầu khí & Năng lượng (9)
    "GAS", "PVD", "PVS", "BSR", "PLX", "PVT", "PVC", "PVB", "OIL",
    # Bán lẻ & Tiêu dùng (10)
    "MWG", "FRT", "PNJ", "DGW", "MSN", "PET", "VNM", "SAB", "DBC", "BAF",
    # Thép & Vật liệu (7)
    "HPG", "HSG", "NKG", "VGS", "TLH", "KSB", "BMP",
    # Hóa chất & Phân bón (8)
    "DGC", "CSV", "DPM", "DCM", "BFC", "LAS", "DDV", "GVR",
    # Vận tải biển & Logistics (6)
    "GMD", "HAH", "VSC", "VOS", "VIP", "VTO",
    # Tiềm năng & Ngách khác (6)
    "NVB", "NT2", "IDC", "HAG", "PC1", "CTR"
]

_SCAN_CACHE = {
    "timestamp": 0,
    "date": "",
    "data": None
}

def scan_full_market(force_refresh=False) -> dict:
    """
    Rà soát toàn bộ thị trường đa luồng và phân loại thành các tầng tín hiệu.
    Tự động cache 300 giây (5 phút) để tối ưu tốc độ phản hồi trên di động.
    """
    global _SCAN_CACHE
    now_ts = time.time()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if not force_refresh and _SCAN_CACHE["data"] is not None and (now_ts - _SCAN_CACHE["timestamp"] < 300):
        return _SCAN_CACHE["data"]
        
    def evaluate_item(sym):
        try:
            res = score_bdi_stock(sym)
            if not res or res.get("status") == "error":
                return None
            
            sec_key = SYMBOL_SECTOR_LOOKUP.get(sym, "KHAC")
            sec_cfg = SECTOR_TIERS_CONFIG.get(sec_key, {})
            sec_name = sec_cfg.get("name", "HOSE")
            
            item = {
                "symbol": sym,
                "sector": sec_name,
                "close": float(res.get("close", 0.0)),
                "chg_pct": float(res.get("chg_pct", 0.0)),
                "vol_r10": float(res.get("vol_r10", 1.0)),
                "avg_vol10": float(res.get("avg_vol10", 0.0)),
                "bdi_score": int(res.get("bdi_score", 50)),
                "point_code": res.get("point_code", "NONE"),
                "point_name": res.get("point_name", "Tích lũy"),
                "is_volume_surge": bool(res.get("is_volume_surge", False)),
                "is_base_valid": bool(res.get("is_base_valid", False)),
                "base_setup_desc": str(res.get("base_setup_desc", "")),
                "base_setup_meta": res.get("base_setup_meta", {}),
                "recommendation": res.get("recommendation", "Theo dõi"),
                "low_buy": float(res.get("low_buy", 0.0)),
                "criteria": res.get("criteria", [])
            }
            return item
        except Exception:
            return None

    # Tải trước bảng giá trực tuyến batch 1 lần duy nhất (~4s) cho toàn bộ 83 mã
    try:
        preload_live_price_board(SCAN_UNIVERSE)
    except Exception:
        pass

    with ThreadPoolExecutor(max_workers=8) as executor:
        raw_items = list(executor.map(evaluate_item, SCAN_UNIVERSE))
        
    items = [it for it in raw_items if it is not None]
    
    # Phân loại theo tiêu chuẩn
    pivots = []
    daynen = []
    cuoc = []
    vol_surge = []
    
    for it in items:
        # 1. Đột biến thể tích sớm (Vol Surge >= 2.5x TB10, TB10 >= 50k cp)
        if it["is_volume_surge"] or (it["vol_r10"] >= 2.5 and it["avg_vol10"] >= 50000 and it["chg_pct"] >= 1.0):
            vol_surge.append(it)
            
        # 2. Tầng 3: Pivot / Breakout
        if it["point_code"] == "B1" or "Breakout" in it["point_name"] or "Pivot" in it["point_name"] or (it["vol_r10"] >= 1.25 and it["chg_pct"] >= 2.0 and it["bdi_score"] >= 65):
            pivots.append(it)
            
        # 3. Tầng 2: Đẩy nền (Pocket Pivot / Base Push)
        if it["point_code"] == "P1" or "Đẩy Nền" in it["point_name"] or (it["vol_r10"] >= 0.9 and it["vol_r10"] <= 1.8 and it["chg_pct"] > 0 and it["bdi_score"] >= 55):
            daynen.append(it)
            
        # 4. Tầng 1: Điểm cược cạn vol (C1)
        # BẮT BUỘC đạt chuẩn Thuật toán số 2: đã qua kiểm tra setup nền mới tối thiểu 1 tuần, có rũ bỏ & kiệt cung
        if it["point_code"] == "C1" or ("Cược" in it["point_name"] and it.get("is_base_valid", False)):
            cuoc.append(it)
            
    # Sắp xếp theo BDI score giảm dần
    pivots.sort(key=lambda x: (x["bdi_score"], x["vol_r10"]), reverse=True)
    daynen.sort(key=lambda x: (x["bdi_score"], x["vol_r10"]), reverse=True)
    cuoc.sort(key=lambda x: (x["bdi_score"], -x["vol_r10"]), reverse=True)
    vol_surge.sort(key=lambda x: (x["vol_r10"], x["bdi_score"]), reverse=True)
    
    scan_result = {
        "timestamp": now_ts,
        "date_str": today_str,
        "time_str": datetime.now().strftime("%H:%M:%S"),
        "total_scanned": len(items),
        "pivots": pivots,
        "daynen": daynen,
        "cuoc": cuoc,
        "vol_surge": vol_surge
    }
    
    _SCAN_CACHE = {
        "timestamp": now_ts,
        "date": today_str,
        "data": scan_result
    }
    
    return scan_result

# ==============================================================================
# HÀM ĐỊNH DẠNG TIN NHẮN TELEGRAM (MOBILE-FRIENDLY HTML FORMATTER)
# ==============================================================================

def format_telegram_scan_result(scan_type: str, force_refresh=False) -> tuple[str, list]:
    """
    Tạo tin nhắn báo cáo đẹp mắt cho Telegram và danh sách nút bấm InlineKeyboard.
    scan_type: 'PIVOT', 'DAYNEN', 'CUOC', 'SURGE', 'ALL'
    """
    res = scan_full_market(force_refresh=force_refresh)
    cur_time = res["time_str"]
    total = res["total_scanned"]
    
    inline_buttons = []
    
    if scan_type == "PIVOT":
        items = res["pivots"][:5] # Lấy Top 5
        title = "🌟 <b>[RADAR VSA - KẾT QUẢ QUÉT PIVOT SÀN HOSE]</b>"
        sub = "Sàng lọc Tầng 3: Bùng nổ vượt cản, Pocket Pivot bứt phá nền giá"
        icon = "🌟"
    elif scan_type == "DAYNEN":
        items = res["daynen"][:5]
        title = "🌱 <b>[RADAR VSA - KẾT QUẢ QUÉT ĐẨY NỀN TẤT CẢ]</b>"
        sub = "Sàng lọc Tầng 2: Tiền vào sớm trong nền, kiểm tra cung thành công"
        icon = "🌱"
    elif scan_type == "CUOC":
        items = res["cuoc"][:5]
        title = "🎯 <b>[RADAR VSA - KẾT QUẢ QUÉT ĐIỂM CƯỢC SÀN HOSE]</b>"
        sub = "Sàng lọc Tầng 1: Nền siết chặt cạn cung đáy, kiệt vol an toàn"
        icon = "🎯"
    elif scan_type == "SURGE":
        items = res["vol_surge"][:5]
        title = "🔥 <b>[RADAR VSA - ĐỘT BIẾN THỂ TÍCH SỚM (VOL SURGE)]</b>"
        sub = "Thanh khoản bùng nổ ≥ 2.5x TB10: Săn siêu cổ phiếu ngách từ chân sóng"
        icon = "🔥"
    else: # ALL
        title = "⚡ <b>[RADAR VSA - TỔNG HỢP CƠ HỘI TOÀN SÀN]</b>"
        sub = "Chắt lọc các cơ hội nổi bật nhất ở cả 3 tầng điểm mua"
        icon = "⚡"
        # Lấy top 2 của mỗi loại
        items = []
        for it in res["vol_surge"][:2]:
            it["tag"] = "🔥 Vol Surge"
            items.append(it)
        for it in res["pivots"][:2]:
            if it not in items:
                it["tag"] = "🌟 Pivot"
                items.append(it)
        for it in res["daynen"][:2]:
            if it not in items:
                it["tag"] = "🌱 Đẩy Nền"
                items.append(it)
        for it in res["cuoc"][:2]:
            if it not in items:
                it["tag"] = "🎯 Điểm Cược"
                items.append(it)
                
    header = (
        f"{title}\n"
        f"⏰ <i>Thời gian quét: {cur_time} • Rà soát: {total} mã HOSE</i>\n"
        f"📝 <i>{sub}</i>\n"
        f"-----------------------------------------\n"
    )
    
    regime_line = ""
    try:
        from market_regime import get_market_regime_footer_line
        regime_line = get_market_regime_footer_line()
    except Exception:
        pass

    if not items:
        body = (
            "⚪ <i>Hiện tại chưa có mã nào thỏa mãn đầy đủ tiêu chí của bộ lọc này.</i>\n\n"
            "💡 <b>Lời khuyên kỷ luật:</b> Thị trường đang trong giai đoạn tích lũy hoặc phân hóa, "
            "kiên nhẫn chờ dòng tiền xác nhận, không mua vội vàng."
        )
        if regime_line:
            body += f"\n\n-----------------------------------------\n{regime_line}"
        return header + body, []
        
    lines = []
    btn_row = []
    
    for idx, it in enumerate(items, 1):
        sym = it["symbol"]
        sec = it.get("sector", "HOSE")
        p = it["close"]
        chg = it["chg_pct"]
        vol_r = it["vol_r10"]
        bdi = it["bdi_score"]
        p_name = it.get("point_name", "")
        low_p = it.get("low_buy", p * 0.97)
        risk_pct = ((p - low_p) / (p + 1e-9)) * 100
        
        chg_sign = "+" if chg > 0 else ""
        vol_tag = "🔥 NỔ VOL" if vol_r >= 2.5 else ("🌱 Vừa chớm" if vol_r >= 1.2 else "Kiệt cung")
        base_desc_str = it.get("base_setup_desc", "")
        base_line = f"\n• Cấu trúc nền: <i>{base_desc_str}</i>" if base_desc_str else ""
        tag_prefix = f"[{it['tag']}] " if "tag" in it else ""
        
        card = (
            f"<b>{idx}. {icon} {tag_prefix}<b>{sym}</b> ({sec})</b>\n"
            f"• Giá: <b>{p:.2f}</b> ({chg_sign}{chg:.2f}%) | Vol: <b>{vol_r:.2f}x</b> TB10 ({vol_tag})\n"
            f"• Điểm BDI: <b>{bdi}/100đ</b> ({it.get('recommendation', 'Mua')})\n"
            f"• Tín hiệu: <i>{p_name}</i>{base_line}\n"
            f"• Mốc cắt lỗ (Low nến): <b>{low_p:.2f}</b> (Rủi ro: -{risk_pct:.1f}%)"
        )
        lines.append(card)
        
        # Thêm nút bấm Inline để user lưu vào Radar chỉ bằng 1 chạm
        btn_row.append({"text": f"📌 Lưu {sym}", "callback_data": f"WATCH_{sym}"})
        
    body = "\n\n".join(lines)
    footer = ""
    if regime_line:
        footer += f"\n\n-----------------------------------------\n{regime_line}"
    footer += (
        "\n-----------------------------------------\n"
        "💡 <i>Bấm nút bên dưới để đưa mã vào Radar tự động bám sát trong phiên:</i>"
    )
    
    # Chia nút thành các hàng 2-3 nút
    inline_keyboard = []
    for i in range(0, len(btn_row), 3):
        inline_keyboard.append(btn_row[i:i+3])
        
    return header + body + footer, inline_keyboard
