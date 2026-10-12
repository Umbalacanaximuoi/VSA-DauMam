import os
import sys
import json
import time
import argparse
from datetime import datetime, time as dtime
import requests

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
elif hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')
elif hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Path setup
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
    MEI_DIR = getattr(sys, '_MEIPASS', APP_DIR)
    BASE_DIR = APP_DIR if os.path.exists(os.path.join(APP_DIR, "data_mart")) else MEI_DIR
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_MART_DIR = os.path.join(BASE_DIR, "data_mart")
os.makedirs(DATA_MART_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_MART_DIR, "telegram_config.json")
LOG_FILE = os.path.join(DATA_MART_DIR, "rrbdi_alerts.log")
ALERT_CACHE_FILE = os.path.join(DATA_MART_DIR, "rrbdi_alerted_cache.json")

# =========================================================================
# CẤU HÌNH TẦN SUẤT QUÉT (SCAN INTERVALS)
# 1. Hai danh mục cá nhân (Nắm giữ & Watchlist): Rút ngắn để bám sát nhịp nổ thời gian thực
INTERVAL_2_PORTFOLIOS_BREAKOUT = 300  # 5 phút / lần (09:15 - 14:30)
INTERVAL_2_PORTFOLIOS_BMS = 180       # 3 phút / lần (13:01 - 14:46)
# 2. Toàn thị trường: Giữ nguyên lịch trình quét (14h05, 14h30, 15h02)
# =========================================================================

import threading

sys.path.append(BASE_DIR)
from bdi_engine import (
    load_tracked_positions,
    load_watchlist_positions,
    save_watchlist_position,
    evaluate_rrbdi_for_tracked_positions,
    evaluate_watchlist_signals,
    score_bdi_stock
)
from market_scanner import format_telegram_scan_result, scan_full_market
from bdi_momentum import get_latest_bms_momentum
from market_regime import get_market_regime_footer_line

def get_market_regime_footer() -> str:
    """Trả về dòng trạng thái cảnh báo bối cảnh VN-Index ở cuối mỗi báo cáo."""
    try:
        return get_market_regime_footer_line()
    except Exception:
        return ""

def load_telegram_config():
    """Loads Telegram Bot token and Chat ID."""
    if not os.path.exists(CONFIG_FILE):
        default_cfg = {
            "bot_token": "",
            "chat_id": "",
            "enabled": True,
            "description": "Nhập bot_token (từ @BotFather) và chat_id (từ @userinfobot) để nhận thông báo Telegram."
        }
        os.makedirs(DATA_MART_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_cfg, f, ensure_ascii=False, indent=2)
        return default_cfg
        
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"bot_token": "", "chat_id": "", "enabled": False}

def get_main_reply_keyboard():
    """Bàn phím Menu cố định trên màn hình điện thoại (Mobile Reply Keyboard)."""
    return {
        "keyboard": [
            [{"text": "🏆 Săn Siêu Cổ Nền 2 (No2)"}, {"text": "💎 Radar Siêu Cổ Phiếu AI"}],
            [{"text": "⚡ Cổ phiếu giải phóng năng lượng"}, {"text": "🎯 Kiểm tra Xung Lực BDI"}],
            [{"text": "🌟 Quét Pivot sàn HOSE"}, {"text": "🌱 Quét Đẩy Nền tất cả"}],
            [{"text": "🔥 Quét Nổ Vol Surge"}, {"text": "💼 Xem Danh Mục Nắm Giữ"}],
            [{"text": "📡 Xem Radar Watchlist"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }


def send_telegram_alert(text: str, reply_markup: dict = None, chat_id_override: str = None) -> bool:
    """Sends a message via Telegram Bot API with optional reply_markup and chat_id override."""
    cfg = load_telegram_config()
    token = cfg.get("bot_token", "").strip()
    chat_id = chat_id_override or cfg.get("chat_id", "").strip()
    enabled = cfg.get("enabled", True)
    
    # Log to file regardless
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}]\n{text}\n" + "="*50 + "\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)
        
    print(f"\n[ALERT GENERATED - {timestamp}]:\n{text}")
    
    if not enabled or not token or not chat_id:
        print("⚠️ Telegram chưa cấu hình Token hoặc Chat ID. Vui lòng cập nhật data_mart/telegram_config.json")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    # Gắn bàn phím menu hoặc nút inline
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    else:
        payload["reply_markup"] = get_main_reply_keyboard()
        
    try:
        resp = requests.post(url, json=payload, timeout=12)
        if resp.status_code == 200:
            print("✅ Đã gửi thông báo Telegram thành công!")
            return True
        else:
            print(f"❌ Lỗi gửi Telegram ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Lỗi kết nối Telegram: {e}")
        return False

def _get_alert_cache():
    if not os.path.exists(ALERT_CACHE_FILE):
        return {"date": "", "sent_keys": []}
    try:
        with open(ALERT_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = datetime.now().strftime("%Y-%m-%d")
            if data.get("date") != today_str:
                return {"date": today_str, "sent_keys": []}
            return data
    except Exception:
        return {"date": "", "sent_keys": []}

def _save_alert_cache(cache):
    try:
        with open(ALERT_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def check_market_open(task_name="Quét", check_trading_hours=False, force=False) -> bool:
    """
    Kiểm tra thị trường có đang mở cửa không.
    Thứ 7 & Chủ Nhật thị trường đóng cửa -> Bỏ qua.
    Nếu check_trading_hours=True -> Chỉ chạy trong khung 09:15 - 14:45.
    Nếu force=True -> Luôn chạy (phục vụ test).
    """
    if force:
        return True
    now = datetime.now()
    if now.weekday() >= 5: # 5 = Thứ 7, 6 = Chủ Nhật
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] {task_name}: Hôm nay là cuối tuần (Thứ 7 / Chủ Nhật), thị trường đóng cửa. Bỏ qua quét.")
        return False
    if check_trading_hours:
        if not (dtime(9, 15) <= now.time() <= dtime(14, 45)):
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] {task_name}: Ngoài khung giờ giao dịch ({now.strftime('%H:%M')}). Bỏ qua quét.")
            return False
    return True

# =========================================================================
# 1. QUÉT ĐIỂM NỔ BREAKOUT 2 DANH MỤC TRONG PHIÊN (RÚT NGẮN: 5 PHÚT / LẦN)
# =========================================================================
def scan_intraday_breakouts(force=False):
    """
    Rà soát độc lập 2 danh mục:
    1. DANH MỤC NẮM GIỮ (HOLDINGS): Cảnh báo điểm nổ để MUA GIA TĂNG TỶ TRỌNG.
    2. DANH MỤC THEO DÕI (WATCHLIST RADAR): Cảnh báo tín hiệu (C1, P1, B1, Vol Surge) để MỞ VỊ THẾ MUA MỚI.
    Tần suất rút ngắn: 5 phút/lần từ 9h15 đến 14h30 Thứ 2 - Thứ 6.
    """
    if not check_market_open("Quét Breakout 2 danh mục (5 phút)", check_trading_hours=True, force=force):
        return
        
    try:
        import evaluator
        evaluator.clear_prepared_dfs_cache()
    except Exception:
        pass

    positions = load_tracked_positions()
    watchlist = load_watchlist_positions()
    
    if not positions and not watchlist:
        print("Cả danh mục nắm giữ và danh sách theo dõi đều rỗng.")
        return
        
    # Tải trước bảng giá thời gian thực cho 2 danh mục cá nhân (khoảng 5-15 mã, chỉ mất ~1.2s)
    try:
        import evaluator
        my_symbols = list(set([p.get("symbol", "").strip() for p in positions if p.get("symbol")] + 
                              [w.get("symbol", "").strip() for w in watchlist if w.get("symbol")]))
        if my_symbols:
            evaluator.preload_live_price_board(my_symbols)
    except Exception:
        pass
        
    cache = _get_alert_cache()
    today_str = datetime.now().strftime("%Y-%m-%d")
    cache["date"] = today_str
    sent_keys = cache.get("sent_keys", [])
    
    breakout_alerts = []
    
    # -------------------------------------------------------------
    # PHẦN 1: QUÉT DANH MỤC NẮM GIỮ (HOLDINGS) -> MUA GIA TĂNG TỶ TRỌNG
    # -------------------------------------------------------------
    scanned_holdings = set()
    for pos in positions:
        sym = pos["symbol"]
        if sym in scanned_holdings:
            continue
        scanned_holdings.add(sym)
        
        bdi_res = score_bdi_stock(sym)
        if bdi_res.get("status") == "error":
            continue
            
        point_code = bdi_res.get("point_code", "NONE")
        vol_r10 = bdi_res.get("vol_r10", 1.0)
        avg_v10 = bdi_res.get("avg_vol10", 1.0)
        chg_pct = bdi_res.get("change_pct", 0.0) if "change_pct" in bdi_res else bdi_res.get("chg_pct", 0.0)
        close = bdi_res.get("close", 0.0)
        bdi = bdi_res.get("bdi_score", 0)
        is_vol_surge = bdi_res.get("is_volume_surge", False) or (vol_r10 >= 2.5 and avg_v10 >= 50000 and chg_pct >= 1.5)
        
        alert_key = f"{sym}_HOLDING_BREAKOUT_{today_str}"
        
        # 1. Đột biến thể tích sớm (Volume Surge Alert >= 2.5x TB10, TB10 >= 50k cp)
        if is_vol_surge:
            if alert_key not in sent_keys:
                breakout_alerts.append(
                    f"🔥 <b>[DANH MỤC NẮM GIỮ - ĐỘT BIẾN THỂ TÍCH SỚM]: {sym}</b>\n"
                    f"• Giá hiện tại: <b>{close:.2f}</b> ({chg_pct:+.2f}%)\n"
                    f"• Khối lượng nổ đột biến: <b>{vol_r10:.2f}x</b> TB10 (TB10: {avg_v10:,.0f} cp)\n"
                    f"• Điểm BDI: <b>{bdi}/100</b>\n"
                    f"• Khuyến nghị: Cổ phiếu đang nắm giữ phát tín hiệu tiền lớn gia nhập mạnh! Kích hoạt <b>MUA GIA TĂNG TỶ TRỌNG</b> ngay!"
                )
                sent_keys.append(alert_key)
        # 2. Điểm nổ Breakout chuẩn (B1)
        elif point_code == "B1" or (vol_r10 >= 1.25 and chg_pct >= 2.3 and bdi >= 68):
            if alert_key not in sent_keys:
                breakout_alerts.append(
                    f"🚀 <b>[DANH MỤC NẮM GIỮ - MUA GIA TĂNG BREAKOUT]: {sym}</b>\n"
                    f"• Giá hiện tại: <b>{close:.2f}</b> ({chg_pct:+.2f}%)\n"
                    f"• Khối lượng bùng nổ: <b>{vol_r10:.2f}x</b> TB10\n"
                    f"• Điểm BDI: <b>{bdi}/100</b>\n"
                    f"• Khuyến nghị: Vị thế đang lãi tiếp tục bứt phá nền, kích hoạt <b>MUA BỒI ĐỦ TỶ TRỌNG (ĐỢT 2)</b>!"
                )
                sent_keys.append(alert_key)

    # -------------------------------------------------------------
    # PHẦN 2: QUÉT DANH MỤC THEO DÕI (WATCHLIST RADAR) -> MỞ VỊ THẾ MUA MỚI
    # -------------------------------------------------------------
    scanned_watchlist = set()
    for w in watchlist:
        sym = w["symbol"]
        if sym in scanned_watchlist:
            continue
        scanned_watchlist.add(sym)
        
        bdi_res = score_bdi_stock(sym)
        if bdi_res.get("status") == "error":
            continue
            
        point_code = bdi_res.get("point_code", "NONE")
        vol_r10 = bdi_res.get("vol_r10", 1.0)
        avg_v10 = bdi_res.get("avg_vol10", 1.0)
        chg_pct = bdi_res.get("change_pct", 0.0) if "change_pct" in bdi_res else bdi_res.get("chg_pct", 0.0)
        close = bdi_res.get("close", 0.0)
        bdi = bdi_res.get("bdi_score", 0)
        is_vol_surge = bdi_res.get("is_volume_surge", False) or (vol_r10 >= 2.5 and avg_v10 >= 50000 and chg_pct >= 1.5)
        
        alert_key = f"{sym}_WATCHLIST_SIGNAL_{today_str}"
        
        # 1. Đột biến thể tích sớm (Volume Surge Alert)
        if is_vol_surge:
            if alert_key not in sent_keys:
                breakout_alerts.append(
                    f"🎯 <b>[WATCHLIST RADAR - ĐỘT BIẾN THỂ TÍCH SỚM]: {sym}</b>\n"
                    f"• Giá hiện tại: <b>{close:.2f}</b> ({chg_pct:+.2f}%)\n"
                    f"• Khối lượng nổ đột biến: <b>{vol_r10:.2f}x</b> TB10 (TB10: {avg_v10:,.0f} cp)\n"
                    f"• Điểm BDI: <b>{bdi}/100</b>\n"
                    f"• Khuyến nghị: Cổ phiếu trong danh sách theo dõi vừa nổ Vol chân sóng! Kích hoạt <b>MỞ VỊ THẾ MUA MỚI</b> ngay!"
                )
                sent_keys.append(alert_key)
        # 2. Điểm nổ Breakout chuẩn (B1)
        elif point_code == "B1" or (vol_r10 >= 1.25 and chg_pct >= 2.3 and bdi >= 68):
            if alert_key not in sent_keys:
                breakout_alerts.append(
                    f"🚀 <b>[WATCHLIST RADAR - ĐIỂM NỔ BREAKOUT MỞ MUA]: {sym}</b>\n"
                    f"• Giá hiện tại: <b>{close:.2f}</b> ({chg_pct:+.2f}%)\n"
                    f"• Khối lượng bùng nổ: <b>{vol_r10:.2f}x</b> TB10\n"
                    f"• Điểm BDI: <b>{bdi}/100</b>\n"
                    f"• Khuyến nghị: Bứt phá dứt khoát khỏi nền tích lũy! Đạt tiêu chuẩn <b>MỞ VỊ THẾ MUA CHUẨN (B1)</b>!"
                )
                sent_keys.append(alert_key)
        # 3. Pivot đẩy nền (P1)
        elif point_code == "P1":
            if alert_key not in sent_keys:
                breakout_alerts.append(
                    f"🌱 <b>[WATCHLIST RADAR - PIVOT ĐẨY NỀN]: {sym}</b>\n"
                    f"• Giá hiện tại: <b>{close:.2f}</b> ({chg_pct:+.2f}%)\n"
                    f"• Khối lượng nhú Pivot: <b>{vol_r10:.2f}x</b> TB10\n"
                    f"• Điểm BDI: <b>{bdi}/100</b>\n"
                    f"• Khuyến nghị: Tiền vào sớm nhú khỏi hỗ trợ MA20. Đạt điều kiện <b>MỞ VỊ THẾ THĂM DÒ (P1)</b>!"
                )
                sent_keys.append(alert_key)
        # 4. Điểm cược cạn vol (C1)
        elif point_code == "C1":
            if alert_key not in sent_keys:
                breakout_alerts.append(
                    f"🎯 <b>[WATCHLIST RADAR - ĐIỂM CƯỢC C1 CHÂN SÓNG]: {sym}</b>\n"
                    f"• Giá hiện tại: <b>{close:.2f}</b> ({chg_pct:+.2f}%)\n"
                    f"• Khối lượng cạn kiệt: <b>{vol_r10:.2f}x</b> TB10\n"
                    f"• Điểm BDI: <b>{bdi}/100</b>\n"
                    f"• Khuyến nghị: Nền siết chặt cạn cung đáy. Đạt tiêu chuẩn <b>MỞ MUA CƯỢC TEST NỀN (C1)</b>!"
                )
                sent_keys.append(alert_key)
                
    cache["sent_keys"] = sent_keys
    _save_alert_cache(cache)
    
    if breakout_alerts:
        header = f"⚡ <b>[RRBDI - CẢNH BÁO BÙNG NỔ TRONG PHIÊN {datetime.now().strftime('%H:%M')}]</b>\n"
        footer = get_market_regime_footer()
        footer_block = f"\n\n-----------------------------------------\n{footer}" if footer else ""
        msg = header + "\n\n".join(breakout_alerts) + footer_block
        send_telegram_alert(msg)
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Quét 5 phút (2 danh mục): Không có mã nào xuất hiện tín hiệu mới.")

# =========================================================================
# 1B. QUÉT XUNG LỰC BDI (BMS) - GIẢI PHÓNG NĂNG LƯỢNG (RÚT NGẮN: 3 PHÚT / LẦN: 13h01 - 14h46)
# =========================================================================
def scan_bms_momentum_alerts(force=False, chat_id_override=None):
    """
    Rà soát độc lập 2 danh mục:
    1. DANH MỤC THEO DÕI (WATCHLIST RADAR): Cảnh báo khi BMS >= 80đ (Hạng A) để MỞ VỊ THẾ CƯỢC 1/8 hoặc ĐÓN ĐẦU ĐẨY NỀN.
    2. DANH MỤC ĐÃ MUA (HOLDINGS): Cảnh báo khi BMS >= 80đ để MUA GIA TĂNG FULL HÀNG (hoặc kích hoạt Margin khi đã bứt nền).
    Khung giờ: 13h01 đến 14h46, tần suất rút ngắn 3 phút/lần.
    """
    now = datetime.now()
    if not force:
        weekday = now.weekday()
        if weekday >= 5:
            return
        if not (dtime(13, 1) <= now.time() <= dtime(14, 46)):
            print(f"[{now.strftime('%H:%M:%S')}] Quét BMS: Ngoài khung giờ 13h01 - 14h46. Bỏ qua.")
            return

    try:
        import evaluator
        evaluator.clear_prepared_dfs_cache()
    except Exception:
        pass

    positions = load_tracked_positions()
    watchlist = load_watchlist_positions()
    
    if not positions and not watchlist:
        if chat_id_override:
            send_telegram_alert("⚠️ <i>Cả danh mục nắm giữ và danh sách theo dõi đều đang trống. Hãy thêm mã vào để quét Xung Lực BMS!</i>", chat_id_override=chat_id_override)
        return

    # Tải trước bảng giá thời gian thực cho 2 danh mục cá nhân
    try:
        import evaluator
        my_symbols = list(set([p.get("symbol", "").strip() for p in positions if p.get("symbol")] + 
                              [w.get("symbol", "").strip() for w in watchlist if w.get("symbol")]))
        if my_symbols:
            evaluator.preload_live_price_board(my_symbols)
    except Exception:
        pass

    cache = _get_alert_cache()
    today_str = datetime.now().strftime("%Y-%m-%d")
    cache["date"] = today_str
    sent_keys = cache.get("sent_keys", [])
    
    bms_alerts = []
    
    # 1. Quét Danh Mục Đã Mua (Holdings) -> Mua Gia Tăng hoặc Kích Hoạt Margin
    scanned_holdings = set()
    for pos in positions:
        sym = pos["symbol"]
        if sym in scanned_holdings:
            continue
        scanned_holdings.add(sym)
        
        res = get_latest_bms_momentum(sym)
        if res.get("status") != "success":
            continue
            
        bms_score = res.get("bms_score", 0.0)
        close = res.get("close", 0.0)
        chg = res.get("chg_pct", 0.0)
        vol_r20 = res.get("vol_ratio_20", 1.0)
        vol = res.get("volume", 0)
        subs = res.get("sub_scores", {})
        
        # Tiêu chuẩn Giải phóng năng lượng: BMS >= 80 (Hạng A)
        if bms_score >= 80.0:
            alert_key = f"{sym}_HOLDING_BMS_A_{today_str}"
            if alert_key not in sent_keys or force:
                msg = (
                    f"🚀 <b>[DANH MỤC ĐÃ MUA - XUNG LỰC BÙNG NỔ BMS]: {sym}</b>\n"
                    f"• Giá hiện tại: <b>{close:.2f}</b> ({chg:+.2f}%)\n"
                    f"• Điểm Xung Lực: <b>{bms_score}/100</b> | {res['badge']}\n"
                    f"• Khối lượng: <b>{vol_r20:.2f}x</b> TB20 (Khớp: {vol:,} cp)\n"
                    f"• Chi tiết: RS: {subs.get('rs', 0)}đ | VDU: {subs.get('vdu', 0)}đ | VCP: {subs.get('vcp', 0)}đ | SMD: {subs.get('smd', 0)}đ | PA: {subs.get('pa', 0)}đ\n"
                    f"• <b>Chiến lược hành động:</b>\n"
                    f"  👉 Vị thế có sẵn đang đón nhận dòng tiền xung lực cực đại! Đạt tiêu chuẩn <b>MUA GIA TĂNG FULL HÀNG (ĐỢT 2)</b>!\n"
                    f"  👉 Nếu giá đã bứt phá thoát nền thành công và có đệm lãi dày ≥ 8%, chuẩn bị điều kiện <b>KÍCH HOẠT MARGIN (KCN 4)</b>!"
                )
                bms_alerts.append(msg)
                if not force:
                    sent_keys.append(alert_key)
                    
    # 2. Quét Danh Mục Theo Dõi (Watchlist) -> Mở Vị Thế Cược 1/8 hoặc Đẩy Nền
    scanned_watchlist = set()
    for w in watchlist:
        sym = w["symbol"]
        if sym in scanned_watchlist:
            continue
        scanned_watchlist.add(sym)
        
        res = get_latest_bms_momentum(sym)
        if res.get("status") != "success":
            continue
            
        bms_score = res.get("bms_score", 0.0)
        close = res.get("close", 0.0)
        chg = res.get("chg_pct", 0.0)
        vol_r20 = res.get("vol_ratio_20", 1.0)
        vol = res.get("volume", 0)
        subs = res.get("sub_scores", {})
        
        # 2.1 Cảnh báo Giải phóng năng lượng BMS >= 80
        if bms_score >= 80.0:
            alert_key = f"{sym}_WATCHLIST_BMS_A_{today_str}"
            if alert_key not in sent_keys or force:
                msg = (
                    f"🔥 <b>[RADAR THEO DÕI - GIẢI PHÓNG NĂNG LƯỢNG BMS]: {sym}</b>\n"
                    f"• Giá hiện tại: <b>{close:.2f}</b> ({chg:+.2f}%)\n"
                    f"• Điểm Xung Lực: <b>{bms_score}/100</b> | {res['badge']}\n"
                    f"• Khối lượng: <b>{vol_r20:.2f}x</b> TB20 (Khớp: {vol:,} cp)\n"
                    f"• Chi tiết: RS: {subs.get('rs', 0)}đ | VDU: {subs.get('vdu', 0)}đ | VCP: {subs.get('vcp', 0)}đ | SMD: {subs.get('smd', 0)}đ | PA: {subs.get('pa', 0)}đ\n"
                    f"• <b>Chiến lược hành động:</b>\n"
                    f"  👉 Lò xo nén cực đại bung chốt! Đạt điều kiện <b>MỞ VỊ THẾ MUA CƯỢC 1/8 TẠI NỀN</b> hoặc <b>MUA ĐẨY NỀN POCKET PIVOT</b>!\n"
                    f"  ⚠️ <i>Lưu ý: Tuyệt đối KHÔNG dùng Margin tại nền. Chỉ dùng tiền thịt.</i>"
                )
                bms_alerts.append(msg)
                if not force:
                    sent_keys.append(alert_key)

        # 2.2 Kiểm tra Dấu hiệu Kiệt Cung (No Supply / Kiệt Vol tại nền)
        vdu_score = subs.get('vdu', 0.0)
        vol_r10_val = res.get('vol_ratio_10', vol_r20)
        is_kiet_cung = (vol_r20 <= 0.75 or vol_r10_val <= 0.75) and abs(chg) <= 2.2 and vdu_score >= 15.0
        if is_kiet_cung:
            alert_key_kc = f"{sym}_WATCHLIST_KIETCUNG_{today_str}"
            if alert_key_kc not in sent_keys or force:
                msg_kc = (
                    f"🎯 <b>[RADAR THEO DÕI - PHÁT HIỆN KIỆT CUNG (NO SUPPLY)]: {sym}</b>\n"
                    f"• Giá hiện tại: <b>{close:.2f}</b> ({chg:+.2f}%)\n"
                    f"• Khối lượng: <b>{vol_r20:.2f}x</b> TB20 (Cạn kiệt lực bán: {vol:,} cp)\n"
                    f"• Động lực kiệt cung (VDU): <b>{subs.get('vdu', 0)}/25đ</b> | Độ nén VCP: <b>{subs.get('vcp', 0)}/20đ</b>\n"
                    f"• <b>Chiến lược hành động:</b>\n"
                    f"  👉 Lực bán trôi nổi đã cạn kiệt, rủi ro sụt giảm thấp nhất! Đạt điều kiện <b>MỞ VỊ THẾ MUA CƯỢC 1/8 TẠI NỀN (TẦNG 1)</b> để đón đầu trước giờ G!\n"
                    f"  🛡️ <i>Cắt lỗ kỷ luật: Thủng đáy thanh nến kiệt cung hôm nay.</i>"
                )
                bms_alerts.append(msg_kc)
                if not force:
                    sent_keys.append(alert_key_kc)
                    
    if not force:
        cache["sent_keys"] = sent_keys
        _save_alert_cache(cache)
        
    if bms_alerts:
        header = f"⚡ <b>[RRBDI - CẢNH BÁO XUNG LỰC BMS GIẢI PHÓNG NĂNG LƯỢNG ({datetime.now().strftime('%H:%M')})]</b>\n"
        footer = get_market_regime_footer()
        footer_block = f"\n\n-----------------------------------------\n{footer}" if footer else ""
        full_msg = header + "\n\n" + "\n\n".join(bms_alerts) + footer_block
        send_telegram_alert(full_msg, chat_id_override=chat_id_override)
    else:
        if chat_id_override or force:
            send_telegram_alert(f"📡 <b>[RADAR BMS 3 PHÚT]</b>: Đã quét danh mục lúc {datetime.now().strftime('%H:%M')}. Chưa có mã nào đạt điểm BMS Hạng A (≥ 80đ).", chat_id_override=chat_id_override)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Quét BMS 3p: Không có mã nào đạt ngưỡng giải phóng năng lượng.")

# =========================================================================
# 2. QUÉT PHIÊN CHIỀU (LÚC 14h05 - SAU 2h CHIỀU 1 LẦN)
# =========================================================================
def scan_afternoon_14h(force=False):
    """
    Rà soát toàn diện danh mục lúc 14h05 để nắm bắt xu hướng phiên chiều (Thứ 2 - Thứ 6).
    """
    if not check_market_open("Rà soát phiên chiều 14h05", check_trading_hours=False, force=force):
        return
        
    try:
        import evaluator
        evaluator.clear_prepared_dfs_cache()
    except Exception:
        pass

    results = evaluate_rrbdi_for_tracked_positions()
    if not results:
        print("Danh mục theo dõi rỗng.")
        return
        
    warn_items = []
    safe_items = []
    
    for r in results:
        sym = r['symbol']
        cp = r['current_price']
        pnl = r['profit_pct']
        lvl = r['rrbdi_level']
        badge = r['rrbdi_badge']
        alert = r['rrbdi_alert']
        next_buy = r.get('next_buy_signal')
        
        line = f"• <b>{sym}</b>: Giá {cp:.2f} ({pnl:+.1f}%) | {badge}\n  └ <i>{alert}</i>"
        if next_buy:
            line += f"\n  └ 🌟 <b>{next_buy}</b>"
            
        if lvl in ["YELLOW", "ORANGE", "RED"]:
            warn_items.append(line)
        else:
            safe_items.append(line)
            
    header = (
        f"🕒 <b>[RRBDI - RÀ SOÁT PHIÊN CHIỀU 14h05]</b>\n"
        f"📅 Ngày: {datetime.now().strftime('%d/%m/%Y')} | Dòng tiền chiều định hình\n"
        f"-----------------------------------------\n"
    )
    
    body = ""
    if warn_items:
        body += "⚠️ <b>CÁC MÃ CẦN CHÚ Ý QUẢN TRỊ RỦI RO:</b>\n" + "\n".join(warn_items) + "\n\n"
    if safe_items:
        body += "🟢 <b>CÁC MÃ DUY TRÌ AN TOÀN / MUA GIA TĂNG:</b>\n" + "\n".join(safe_items)
        
    footer = get_market_regime_footer()
    footer_block = f"\n\n-----------------------------------------\n{footer}" if footer else ""
    send_telegram_alert(header + body + footer_block)

# =========================================================================
# 3. QUÉT KHẨN CẤP TRƯỚC PHIÊN ATC (LÚC 14h30)
# =========================================================================
def scan_pre_atc_1430(force=False):
    """
    Rà soát cấp bách lúc 14h30 để cân nhắc THOÁT HÀNG / BÁN CẮT LỖ trước khi đóng cửa (Thứ 2 - Thứ 6).
    """
    if not check_market_open("Rà soát trước ATC 14h30", check_trading_hours=False, force=force):
        return
        
    try:
        import evaluator
        evaluator.clear_prepared_dfs_cache()
    except Exception:
        pass

    results = evaluate_rrbdi_for_tracked_positions()
    if not results:
        return
        
    red_alerts = []
    orange_alerts = []
    add_alerts = []
    
    for r in results:
        sym = r['symbol']
        cp = r['current_price']
        pnl = r['profit_pct']
        lvl = r['rrbdi_level']
        alert = r['rrbdi_alert']
        next_buy = r.get('next_buy_signal')
        
        if lvl == "RED":
            red_alerts.append(f"🚨 <b>{sym}</b>: Giá {cp:.2f} ({pnl:+.1f}%)\n  └ <b>HÀNH ĐỘNG: BÁN SẠCH 100% TRƯỚC HOẶC TRONG ATC!</b>\n  └ Lý do: {alert}")
        elif lvl == "ORANGE":
            orange_alerts.append(f"🟠 <b>{sym}</b>: Giá {cp:.2f} ({pnl:+.1f}%)\n  └ <b>HÀNH ĐỘNG: HẠ 50% TỶ TRỌNG TRONG ATC!</b>\n  └ Lý do: {alert}")
            
        if next_buy:
            add_alerts.append(f"🚀 <b>{sym}</b>: {next_buy}")
            
    if red_alerts or orange_alerts or add_alerts:
        header = (
            f"🔔 <b>[RRBDI - CẢNH BÁO KHẨN CẤP TRƯỚC ATC 14h30]</b>\n"
            f"⏰ Hãy kiểm tra lệnh ngay trước khi phiên ATC bắt đầu!\n"
            f"-----------------------------------------\n"
        )
        body = ""
        if red_alerts:
            body += "🚨 <b>LỆNH BÁN CẮT LỖ TUYỆT ĐỐI (CẤP ĐỎ):</b>\n" + "\n".join(red_alerts) + "\n\n"
        if orange_alerts:
            body += "🟠 <b>LỆNH HẠ 50% TỶ TRỌNG (CẤP CAM):</b>\n" + "\n".join(orange_alerts) + "\n\n"
        if add_alerts:
            body += "🌟 <b>ĐIỂM MUA GIA TĂNG HỢP LỆ:</b>\n" + "\n".join(add_alerts)
            
        footer = get_market_regime_footer()
        footer_block = f"\n\n-----------------------------------------\n{footer}" if footer else ""
        send_telegram_alert(header + body + footer_block)
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 14h30: Toàn bộ danh mục an toàn, không có lệnh bán khẩn cấp.")

# =========================================================================
# 4. QUÉT TỔNG KẾT KẾT PHIÊN EOD (LÚC 15h02)
# =========================================================================
def scan_eod_1502(force=False):
    """
    Rà soát chốt phiên lúc 15h02 sau khi Metakit cập nhật dữ liệu EOD đầy đủ (Thứ 2 - Thứ 6).
    """
    if not check_market_open("Tổng kết kết phiên EOD 15h02", check_trading_hours=False, force=force):
        return
        
    try:
        import evaluator
        evaluator.clear_prepared_dfs_cache()
    except Exception:
        pass

    results = evaluate_rrbdi_for_tracked_positions()
    if not results:
        print("Danh mục theo dõi rỗng.")
        return
        
    header = (
        f"📊 <b>[RRBDI - BÁO CÁO TỔNG KẾT PHIÊN 15h02]</b>\n"
        f"📅 Ngày: {datetime.now().strftime('%d/%m/%Y')} | Dữ liệu EOD hoàn tất\n"
        f"-----------------------------------------\n"
    )
    
    lines = []
    for r in results:
        sym = r['symbol']
        bp = r['buy_price']
        cp = r['current_price']
        pnl = r['profit_pct']
        badge = r['rrbdi_badge']
        cur_bdi = r.get('current_bdi', 50)
        alert = r['rrbdi_alert']
        
        status_line = f"{badge} <b>{sym}</b> | Mua: {bp:.2f} -> Đóng cửa: <b>{cp:.2f}</b> ({pnl:+.1f}%) | BDI: {cur_bdi}\n  └ <i>{alert}</i>"
        lines.append(status_line)
        
    footer = get_market_regime_footer()
    footer_block = f"\n\n-----------------------------------------\n{footer}" if footer else ""
    body = "\n\n".join(lines) + "\n\n🎯 <i>Tuân thủ nghiêm ngặt ma trận kỷ luật VSA Đậu Mầm Pro.</i>" + footer_block
    send_telegram_alert(header + body)

# =========================================================================
# 5. XỬ LÝ LỆNH TỪ ĐIỆN THOẠI & BỘ QUÉT THEO YÊU CẦU (INTERACTIVE COMMANDS)
# =========================================================================

def format_holdings_for_telegram() -> str:
    try:
        import evaluator
        evaluator.clear_prepared_dfs_cache()
    except Exception:
        pass

    results = evaluate_rrbdi_for_tracked_positions()
    if not results:
        return "💼 <b>[DANH MỤC NẮM GIỮ (HOLDINGS)]:</b>\nHiện tại chưa có vị thế mua nào được ghi nhận."
    
    total_cost = 0
    total_cur = 0
    lines = []
    
    for idx, r in enumerate(results, 1):
        sym = r['symbol']
        bp = r['buy_price']
        cp = r['current_price']
        pnl = r['profit_pct']
        shares = r.get('shares_count', 10000)
        badge = r['rrbdi_badge']
        low_stop = r.get('buy_low', bp * 0.97)
        alert = r.get('rrbdi_alert', 'Bình thường')
        
        cost = bp * shares
        cur = cp * shares
        total_cost += cost
        total_cur += cur
        
        pnl_sign = "+" if pnl > 0 else ""
        lines.append(
            f"<b>{idx}. <b>{sym}</b></b> | Mua: {bp:.2f} ➔ Hiện tại: <b>{cp:.2f}</b> ({pnl_sign}{pnl:.1f}%)\n"
            f"• Số lượng: {shares:,} CP • Trạng thái: {badge}\n"
            f"• Cắt lỗ cứng: <b>{low_stop:.2f}</b>\n"
            f"• Cảnh báo: <i>{alert}</i>"
        )
        
    total_pnl_pct = ((total_cur - total_cost) / (total_cost + 1e-9)) * 100 if total_cost > 0 else 0
    total_sign = "+" if total_pnl_pct > 0 else ""
    
    header = (
        f"💼 <b>[BẢNG 1: DANH MỤC NẮM GIỮ & QUẢN TRỊ VỐN RRBDI]</b>\n"
        f"📊 Số lượng: <b>{len(results)} mã</b> | Tổng PnL: <b>{total_sign}{total_pnl_pct:.2f}%</b>\n"
        f"-----------------------------------------\n"
    )
    footer = get_market_regime_footer()
    footer_block = f"\n\n-----------------------------------------\n{footer}" if footer else ""
    return header + "\n\n".join(lines) + footer_block

def format_watchlist_for_telegram() -> str:
    try:
        import evaluator
        evaluator.clear_prepared_dfs_cache()
    except Exception:
        pass

    results = evaluate_watchlist_signals()
    if not results:
        return "📡 <b>[RADAR THEO DÕI (WATCHLIST)]:</b>\nHiện tại danh sách theo dõi đang trống."
        
    lines = []
    for idx, w in enumerate(results, 1):
        sym = w['symbol']
        p = w.get('current_price', 0.0)
        chg = w.get('today_chg_pct', 0.0)
        vol_r = w.get('vol_r10', 1.0)
        bdi = w.get('current_bdi', 50)
        sig = w.get('signal_badge', 'Chờ tín hiệu')
        adv = w.get('action_advice', 'Quan sát')
        chg_sign = "+" if chg > 0 else ""
        
        lines.append(
            f"<b>{idx}. 📡 <b>{sym}</b></b> | Giá: <b>{p:.2f}</b> ({chg_sign}{chg:.2f}%) | Vol: <b>{vol_r:.2f}x</b>\n"
            f"• Điểm BDI: <b>{bdi}/100đ</b> | Tín hiệu: {sig}\n"
            f"• Khuyến nghị: <i>{adv}</i>"
        )
        
    header = (
        f"📡 <b>[BẢNG 2: DANH SÁCH THEO DÕI (WATCHLIST RADAR)]</b>\n"
        f"🎯 Đang theo dõi: <b>{len(results)} mã tiềm năng</b>\n"
        f"-----------------------------------------\n"
    )
    footer = get_market_regime_footer()
    footer_block = f"\n\n-----------------------------------------\n{footer}" if footer else ""
    return header + "\n\n".join(lines) + footer_block

def format_single_stock_bms(symbol: str) -> str:
    """Bóc tách chi tiết 5 thước đo Xung Lực BMS cho một cổ phiếu cụ thể."""
    try:
        import evaluator
        evaluator.clear_prepared_dfs_cache(symbol)
    except Exception:
        pass
        
    res = get_latest_bms_momentum(symbol, force_reload=True)
    if res.get("status") != "success":
        return f"⚠️ <b>Lỗi:</b> Không thể phân tích xung lực BMS cho mã <b>{symbol.upper()}</b> ({res.get('message', 'Không có dữ liệu')})."
        
    sym = res["symbol"]
    close = res["close"]
    chg = res["chg_pct"]
    bms = res["bms_score"]
    badge = res["badge"]
    vol = res["volume"]
    v_r = res["vol_ratio_20"]
    sub = res["sub_scores"]
    dt = res.get("details", {})
    action = res["action"]
    chg_sign = "+" if chg > 0 else ""
    
    msg = (
        f"📊 <b>[CHI TIẾT XUNG LỰC BDI (BMS) - {sym}]</b>\n"
        f"📅 Ngày: {res.get('date', datetime.now().strftime('%d/%m/%Y'))} | Giá: <b>{close:.2f}</b> ({chg_sign}{chg:.2f}%)\n"
        f"• Khối lượng: <b>{vol:,} cp</b> (<b>{v_r:.2f}x</b> TB20)\n"
        f"-----------------------------------------\n"
        f"🏆 <b>ĐIỂM XUNG LỰC BMS: {bms:.1f}/100đ</b> | {badge}\n\n"
        f"🔍 <b>5 THƯỚC ĐO LƯỢNG HÓA:</b>\n"
        f"1. <b>RS (Sức mạnh so với VNI):</b> <b>{sub['rs']:.1f}/25đ</b>\n"
        f"   └ <i>{dt.get('rs', 'N/A')}</i>\n"
        f"2. <b>VDU (Động lực Vol & Cạn cung):</b> <b>{sub['vdu']:.1f}/25đ</b>\n"
        f"   └ <i>{dt.get('vdu', 'N/A')}</i>\n"
        f"3. <b>VCP (Độ nén lò xo & MA):</b> <b>{sub['vcp']:.1f}/20đ</b>\n"
        f"   └ <i>{dt.get('vcp', 'N/A')}</i>\n"
        f"4. <b>SMD (Dòng tiền ngầm OBV/MACD):</b> <b>{sub['smd']:.1f}/15đ</b>\n"
        f"   └ <i>{dt.get('smd', 'N/A')}</i>\n"
        f"5. <b>PA (Vị thế nến & MA20):</b> <b>{sub['pa']:.1f}/15đ</b>\n"
        f"   └ <i>{dt.get('pa', 'N/A')}</i>\n\n"
        f"🎯 <b>KHUYẾN NGHỊ HÀNH ĐỘNG (4 KIM CHỈ NAM):</b>\n"
        f"👉 <i>{action}</i>"
    )
    regime = get_market_regime_footer()
    if regime:
        msg += f"\n\n-----------------------------------------\n{regime}"
    return msg

def format_portfolio_bms_summary() -> str:
    """Kiểm tra chỉ số Xung Lực BDI cho toàn bộ Danh mục Nắm giữ & Watchlist."""
    try:
        import evaluator
        evaluator.clear_prepared_dfs_cache()
    except Exception:
        pass
        
    positions = load_tracked_positions()
    watchlist = load_watchlist_positions()
    
    if not positions and not watchlist:
        return "⚠️ <i>Cả danh mục nắm giữ và danh sách theo dõi đều đang trống. Hãy thêm mã để kiểm tra Xung Lực BDI!</i>"
        
    lines = []
    
    if positions:
        lines.append("💼 <b>[DANH MỤC ĐÃ MUA (HOLDINGS)]:</b>")
        seen_syms = set()
        count = 1
        for pos in positions:
            sym = pos["symbol"]
            if sym in seen_syms:
                continue
            seen_syms.add(sym)
            res = get_latest_bms_momentum(sym, force_reload=True)
            if res.get("status") == "success":
                c = res["close"]
                chg = res["chg_pct"]
                bms = res["bms_score"]
                badge = res["badge"]
                vr = res["vol_ratio_20"]
                lines.append(f"{count}. <b>{sym}</b>: Giá <b>{c:.2f}</b> ({chg:+.2f}%) | Vol <b>{vr:.2f}x</b> | BMS: <b>{bms:.1f}đ</b> ({badge})")
            else:
                lines.append(f"{count}. <b>{sym}</b>: Đang cập nhật dữ liệu...")
            count += 1
        lines.append("")
        
    if watchlist:
        lines.append("📡 <b>[RADAR THEO DÕI (WATCHLIST)]:</b>")
        seen_w = set()
        count = 1
        for w in watchlist:
            sym = w["symbol"]
            if sym in seen_w:
                continue
            seen_w.add(sym)
            res = get_latest_bms_momentum(sym, force_reload=True)
            if res.get("status") == "success":
                c = res["close"]
                chg = res["chg_pct"]
                bms = res["bms_score"]
                badge = res["badge"]
                vr = res["vol_ratio_20"]
                lines.append(f"{count}. <b>{sym}</b>: Giá <b>{c:.2f}</b> ({chg:+.2f}%) | Vol <b>{vr:.2f}x</b> | BMS: <b>{bms:.1f}đ</b> ({badge})")
            else:
                lines.append(f"{count}. <b>{sym}</b>: Đang cập nhật dữ liệu...")
            count += 1
                
    header = (
        f"🎯 <b>[KIỂM TRA CHỈ SỐ XUNG LỰC BDI (BMS)]</b>\n"
        f"⏰ Thời điểm: {datetime.now().strftime('%H:%M:%S - %d/%m/%Y')}\n"
        f"-----------------------------------------\n"
    )
    regime = get_market_regime_footer()
    regime_block = f"\n-----------------------------------------\n{regime}" if regime else ""
    footer = (
        f"\n💡 <i>Gợi ý: Gõ <b>'xung lực MÃ'</b> (ví dụ: 'xung lực IDC') để bóc tách chi tiết 5 thước đo cho riêng mã đó!</i>"
    )
    return header + "\n".join(lines) + footer + regime_block

def format_market_energy_release_summary() -> str:
    """
    Quét toàn diện: Danh mục riêng + Toàn thị trường
    Tìm các cổ phiếu kích hoạt GIẢI PHÓNG NĂNG LƯỢNG phiên hôm nay (BMS >= 80đ hoặc bùng nổ Breakout/Pocket Pivot).
    """
    try:
        import evaluator
        evaluator.clear_prepared_dfs_cache()
    except Exception:
        pass
        
    holdings = [h['symbol'] for h in load_tracked_positions()]
    watchlist = [w['symbol'] for w in load_watchlist_positions()]
    
    market_peers = [
        "FPT", "MWG", "MSN", "VNM", "VIC", "VHM", "VRE", "VCB", "MBB", "TCB", "CTG", "ACB", "STB", "HDB", "VPB", "TPB",
        "SSI", "VND", "VIX", "HCM", "SHS", "MBS",
        "HPG", "HSG", "NKG",
        "DIG", "DXG", "PDR", "NVL", "KDH", "NLG", "VGC", "KBC", "SZC", "IDC",
        "DGC", "DCM", "DPM", "GVR",
        "PVD", "PVS", "PVT", "BSR",
        "FRT", "DGW", "PNJ",
        "PC1", "REE", "GEG", "NT2", "POW",
        "HAH", "GMD", "VSC",
        "TNG", "VGT", "MSH"
    ]
    universe = list(dict.fromkeys(holdings + watchlist + market_peers))
    
    vni = None
    try:
        import evaluator
        vni = evaluator.get_prepared_stock_df("VNINDEX", force_reload=True)
    except Exception:
        pass
        
    results = []
    for sym in universe:
        try:
            res = get_latest_bms_momentum(sym, vni_df=vni, force_reload=False)
            if res.get("status") == "success":
                tag = "💼 NẮM GIỮ" if sym in holdings else ("📡 THEO DÕI" if sym in watchlist else "🌐 THỊ TRƯỜNG")
                res["tag"] = tag
                results.append(res)
        except Exception:
            pass
            
    # Sắp xếp theo BMS giảm dần
    results.sort(key=lambda x: (x["bms_score"], x["vol_ratio_20"]), reverse=True)
    
    tier_a = [r for r in results if r["bms_score"] >= 80.0]
    tier_b = [r for r in results if 75.0 <= r["bms_score"] < 80.0]
    explosive = [r for r in results if r["chg_pct"] >= 3.5 and r["vol_ratio_20"] >= 1.5 and r not in tier_a]
    
    lines = []
    lines.append(f"⚡ <b>[CỔ PHIẾU GIẢI PHÓNG NĂNG LƯỢNG HÔM NAY]</b>")
    lines.append(f"📅 Ngày: <b>{datetime.now().strftime('%d/%m/%Y')}</b> | Quét <b>{len(universe)} mã</b> thanh khoản cao")
    lines.append("-----------------------------------------\n")
    
    if tier_a or explosive:
        lines.append("🎯 <b>NHÓM HẠNG A (BMS ≥ 80đ) - KHAI HỎA & LÒ XO NÉN CỰC ĐẠI:</b>")
        combined_a = tier_a + explosive
        seen_syms = set()
        for idx, r in enumerate(combined_a, 1):
            s = r["symbol"]
            if s in seen_syms:
                continue
            seen_syms.add(s)
            c = r["close"]
            chg = r["chg_pct"]
            vr = r["vol_ratio_20"]
            bms = r["bms_score"]
            sub = r["sub_scores"]
            
            medals = ["🥇", "🥈", "🥉"]
            medal_str = medals[idx-1] if idx <= 3 else "🔥"
            
            lines.append(
                f"{idx}. <b>[{r['tag']}] {s}</b> | Giá: <b>{c:.2f}</b> ({chg:+.2f}%) | Vol: <b>{vr:.2f}x</b> TB20 {medal_str}\n"
                f"   • BMS: <b>{bms:.1f}/100đ</b> (RS: {sub['rs']} | VDU: {sub['vdu']} | VCP: {sub['vcp']} | SMD: {sub['smd']} | PA: {sub['pa']})\n"
                f"   • <i>{r['action']}</i>"
            )
        lines.append("")
        
    if tier_b:
        lines.append("⏳ <b>NHÓM HẠNG B CAO (75 ≤ BMS < 80đ) - NÉN SÁT GIỜ G:</b>")
        for idx, r in enumerate(tier_b[:6], 1):
            s = r["symbol"]
            c = r["close"]
            chg = r["chg_pct"]
            vr = r["vol_ratio_20"]
            bms = r["bms_score"]
            lines.append(f"• <b>[{r['tag']}] {s}</b>: Giá {c:.2f} ({chg:+.2f}%) | Vol {vr:.2f}x | BMS: <b>{bms:.1f}đ</b>")
        lines.append("")
        
    lines.append(
        "💡 <b>4 KIM CHỈ NAM THỰC CHIẾN:</b>\n"
        "1. Chọn điểm cược 1/8 tại nền khi lò xo nén kiệt vol.\n"
        "2. Gia tăng tỷ trọng khi xuất hiện cây nổ xác nhận (có lãi).\n"
        "3. Cắt lỗ dứt khoát nếu thủng hỗ trợ nền.\n"
        "4. Tuyệt đối KHÔNG dùng Margin tại nền; chỉ kích hoạt khi đã bứt nền & lãi ≥ 8%!"
    )
    
    regime = get_market_regime_footer()
    if regime:
        lines.append("-----------------------------------------")
        lines.append(regime)
        
    return "\n".join(lines)

def format_super_stock_summary(target_sym: str = None) -> str:
    """
    Quét hoặc bóc tách chi tiết mô hình AI Siêu Cổ Phiếu (Super Stock AI Model).
    """
    try:
        from data_pipeline.super_stock_engine import get_super_stock_engine
        engine = get_super_stock_engine()
        
        if target_sym:
            res = engine.score_symbol(target_sym)
            if not res:
                return f"⚠️ <i>Không đủ dữ liệu để tính toán Siêu Cổ Phiếu cho mã {target_sym}.</i>"
            
            p = res["pillars"]
            cp = res["capital_plan"]
            lines = [
                f"💎 <b>[RADAR SIÊU CỔ PHIẾU AI]: {res['symbol']}</b>",
                f"• Điểm Siêu Cổ Phiếu: <b>{res['super_stock_score']}/100</b> ({res['tier_badge']})",
                f"• Giá hiện tại: <b>{res['close']:.2f}</b> ({res['chg_pct']:+.2f}%) | Vol: <b>{res['vol_ratio']:.2f}x</b> TB20",
                f"• Kỳ vọng biên độ sóng: <b>{res['expected_mfe']}</b>",
                f"-----------------------------------------",
                f"🏛️ <b>ĐÁNH GIÁ 5 TRỤ CỘT ĐỊNH LƯỢNG:</b>",
                f"1. {p['gio_dong']['name']}: <b>{p['gio_dong']['score']}đ</b> ({p['gio_dong']['status']})",
                f"2. {p['dan_soi']['name']}: <b>{p['dan_soi']['score']}đ</b> ({p['dan_soi']['status']})",
                f"3. {p['nen_gia']['name']}: <b>{p['nen_gia']['score']}đ</b> ({p['nen_gia']['status']})",
                f"4. {p['xung_luc']['name']}: <b>{p['xung_luc']['score']}đ</b> ({p['xung_luc']['status']})",
                f"5. {p['tennis_ball']['name']}: <b>{p['tennis_ball']['score']}đ</b> ({p['tennis_ball']['status']})",
                f"-----------------------------------------",
                f"📋 <b>KẾ HOẠCH ĐI VỐN & ZERO-LOSS:</b>",
                f"👉 <b>Tầng 1 (Điểm Cược):</b> {cp['entry_bet']}",
                f"👉 <b>Tầng 2 (Gia Tăng):</b> {cp['entry_scale']}",
                f"🛡️ <b>Kỷ Luật Cắt Lỗ:</b> {cp['stop_loss']}",
                f"🎯 <b>Mục Tiêu Chốt Lời:</b> {cp['target']}",
                f"⚡ <b>Margin:</b> {cp['margin_trigger']}"
            ]
            return "\n".join(lines)
        else:
            candidates = engine.scan_radar(min_score=60.0)
            if not candidates:
                return (
                    f"💎 <b>[RADAR SIÊU CỔ PHIẾU AI]</b>\n"
                    f"⏰ Thời điểm: {datetime.now().strftime('%H:%M:%S - %d/%m/%Y')}\n"
                    f"-----------------------------------------\n"
                    f"Hiện tại thị trường chưa xuất hiện điểm nổ thỏa mãn chuẩn Siêu Cổ Phiếu (Điểm ≥ 60/100).\n"
                    f"Hệ thống tiếp tục theo dõi các vùng kiệt cung tại nền giá!"
                )
            
            lines = [
                f"💎 <b>[BẢNG TỔNG HỢP RADAR SIÊU CỔ PHIẾU AI]</b>",
                f"📅 Ngày: <b>{datetime.now().strftime('%d/%m/%Y')}</b> | Tìm thấy <b>{len(candidates)} ứng viên</b> tiềm năng",
                f"-----------------------------------------\n"
            ]
            for idx, c in enumerate(candidates[:10], 1):
                sym = c["symbol"]
                sc = c["super_stock_score"]
                badge = c["tier_badge"]
                p_val = c["close"]
                chg = c["chg_pct"]
                vr = c["vol_ratio"]
                mfe = c["expected_mfe"]
                lines.append(f"{idx}. <b>{sym}</b>: <b>{sc:.1f}/100</b> ({badge}) | Giá <b>{p_val:.2f}</b> ({chg:+.2f}%) | Vol <b>{vr:.2f}x</b> | Mục tiêu: <b>{mfe}</b>")
            
            lines.append("\n💡 <i>Gợi ý: Gõ <b>'siêu cổ MÃ'</b> (ví dụ: 'siêu cổ DGC') để xem chi tiết 5 trụ cột và kế hoạch đi vốn!</i>")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ Lỗi quét Radar Siêu Cổ Phiếu: {e}"

def format_no2_summary(target_sym: str = None) -> tuple:
    """
    Quét hoặc bóc tách chi tiết Chiến Lược Săn Siêu Cổ Nền Số 2 Trên Cao (Strategy No2).
    """
    try:
        from data_pipeline.no2_engine import get_no2_current_candidates, get_no2_detail_for_symbol
        
        if target_sym:
            clean_sym = target_sym.strip().upper()
            res = get_no2_detail_for_symbol(clean_sym)
            if not res or res.get("status") == "error":
                return f"⚠️ <i>Không đủ dữ liệu hoặc lỗi tính toán Chiến Lược No2 cho mã {clean_sym}.</i>", None
            
            p = res.get("pillars", {})
            cp = res.get("capital_plan", {})
            act_status = res.get("action_status", "THEO DÕI")
            no2_score = res.get("no2_score", 0)
            bms_score = res.get("bms_score", 0)
            bms_tier = res.get("bms_tier", "")
            close_val = res.get("close", 0.0)
            s1_gain = res.get("stage1_gain_pct", 0.0)
            b_dur = res.get("base2_duration_days", 0)
            b_dep = res.get("base2_depth_pct", 0.0)
            min_v = res.get("min_vol_ratio_base2", 1.0)
            ma20 = res.get("ma20", 0.0)
            ma50 = res.get("ma50", 0.0)
            ma100 = res.get("ma100", 0.0)
            
            st_icon = "🟢" if res.get("action_code") == "C1" else ("🟡" if res.get("action_code") == "P1" else ("🔵" if res.get("action_code") == "B1" else "⚪"))
            
            lines = [
                f"🏆 <b>[CHIẾN LƯỢC No2 - SĂN NỀN SỐ 2 TRÊN CAO]: {clean_sym}</b>",
                f"• Điểm No2: <b>{no2_score:.1f}/100</b> | Trạng thái: {st_icon} <b>{act_status}</b>",
                f"• Xung lực BMS: <b>{bms_score:.1f}đ</b> ({bms_tier})",
                f"• Giá hiện tại: <b>{close_val:.2f}</b> | MA20: <b>{ma20:.2f}</b> | MA50: <b>{ma50:.2f}</b> | MA100: <b>{ma100:.2f}</b>",
                f"• Độ nén Nền 2: Dài <b>{b_dur} phiên</b> | Độ sâu điều chỉnh: <b>{b_dep:.1f}%</b> | Đáy kiệt vol: <b>{min_v:.2f}x</b> TB20",
                f"-----------------------------------------",
                f"🏛️ <b>ĐỐI CHIẾU 6 TẦNG ĐỊNH LƯỢNG No2:</b>",
                f"1. Tầng 1 (Nhịp tăng 1): {'✅' if p.get('t1_stage1',{}).get('passed') else '❌'} {p.get('t1_stage1',{}).get('desc','')}",
                f"2. Tầng 2 (Bẻ cong xu hướng): {'✅' if p.get('t2_trend_inflection',{}).get('passed') else '❌'} {p.get('t2_trend_inflection',{}).get('desc','')}",
                f"3. Tầng 3 (Cấu trúc Nền 2): {'✅' if p.get('t3_base2_vcp',{}).get('passed') else '❌'} {p.get('t3_base2_vcp',{}).get('desc','')}",
                f"4. Tầng 4 (VSA Cạn cung): {'✅' if p.get('t4_vsa_vdu',{}).get('passed') else '❌'} {p.get('t4_vsa_vdu',{}).get('desc','')}",
                f"5. Tầng 5 (Dòng tiền ngầm): {'✅' if p.get('t5_smd_obv',{}).get('passed') else '❌'} {p.get('t5_smd_obv',{}).get('desc','')}",
                f"6. Tầng 6 (Xung lực & Vị thế): {'✅' if p.get('t6_bms_trigger',{}).get('passed') else '❌'} {p.get('t6_bms_trigger',{}).get('desc','')}",
                f"-----------------------------------------",
                f"📋 <b>KẾ HOẠCH ĐI VỐN THỰC CHIẾN (ZERO-LOSS No2):</b>",
                f"👉 <b>C1 (Cược Trong Nền):</b> {cp.get('entry_c1','')}",
                f"👉 <b>P1 (Pocket Nhú Nền):</b> {cp.get('entry_p1','')}",
                f"👉 <b>B1 (Breakout Sóng 2):</b> {cp.get('entry_b1','')}",
                f"🛡️ <b>Kỷ Luật Cắt Lỗ:</b> {cp.get('stop_loss','')}",
                f"🎯 <b>Mục Tiêu Sóng:</b> {cp.get('target','')}",
                f"⚡ <b>Điều Kiện Margin:</b> {cp.get('margin_trigger','')}"
            ]
            markup = {"inline_keyboard": [[{"text": f"📡 Đưa {clean_sym} Vào Watchlist Radar", "callback_data": f"WATCH_{clean_sym}"}]]}
            return "\n".join(lines), markup
        else:
            candidates = get_no2_current_candidates(min_score=65.0)
            if not candidates:
                return (
                    f"🏆 <b>[RADAR SĂN SIÊU CỔ NỀN SỐ 2 - STRATEGY No2]</b>\n"
                    f"⏰ Thời điểm: {datetime.now().strftime('%H:%M:%S - %d/%m/%Y')}\n"
                    f"-----------------------------------------\n"
                    f"Hiện tại thị trường chưa xuất hiện mã cổ phiếu đạt chuẩn Nền Số 2 (No2 Score ≥ 65/100).\n"
                    f"Hệ thống tiếp tục theo dõi các nhịp nén và cạn cung tại nền!"
                ), None
            
            lines = [
                f"🏆 <b>[BẢNG TỔNG HỢP SĂN SIÊU CỔ NỀN SỐ 2 - STRATEGY No2]</b>",
                f"📅 Ngày: <b>{datetime.now().strftime('%d/%m/%Y')}</b> | Tìm thấy <b>{len(candidates)} ứng viên</b> đang nén chặt",
                f"-----------------------------------------\n"
            ]
            inline_btns = []
            row_btns = []
            for idx, c in enumerate(candidates[:10], 1):
                sym = c["symbol"]
                sc = c.get("no2_score", 0)
                bms = c.get("bms_score", 0)
                act = c.get("action_code", "C1")
                p_val = c.get("close", 0.0)
                dur = c.get("base2_duration_days", 0)
                dep = c.get("base2_depth_pct", 0.0)
                s1 = c.get("stage1_gain_pct", 0.0)
                lines.append(f"{idx}. <b>{sym}</b>: No2 <b>{sc:.1f}đ</b> | BMS <b>{bms:.1f}đ</b> | <b>[{act}]</b> Giá <b>{p_val:.2f}</b> (Nền <b>{dur}p</b> - sâu <b>{dep:.1f}%</b>, Nhịp 1 <b>+{s1:.1f}%</b>)")
                row_btns.append({"text": f"🏆 Soi {sym}", "callback_data": f"NO2_{sym}"})
                if len(row_btns) == 2:
                    inline_btns.append(row_btns)
                    row_btns = []
            if row_btns:
                inline_btns.append(row_btns)
            
            lines.append("\n💡 <i>Gợi ý: Bấm nút bên dưới hoặc gõ <b>'no2 MÃ'</b> (ví dụ: 'no2 VOS', 'no2 PVS') để bóc tách chi tiết 6 tầng!</i>")
            markup = {"inline_keyboard": inline_btns} if inline_btns else None
            return "\n".join(lines), markup
    except Exception as e:
        return f"❌ Lỗi quét Chiến Lược No2: {e}", None

def format_welcome_help() -> str:
    return (
        "🤖 <b>[VSA ĐẬU MẦM PRO - TRỢ LÝ TRADING TELEGRAM]</b>\n\n"
        "Chào mừng bạn đến với hệ thống hỗ trợ ra quyết định VSA Đậu Mầm Pro!\n"
        "Hệ thống vận hành theo <b>4 KIM CHỈ NAM THỰC CHIẾN</b>:\n"
        "1. Chọn điểm mua tốt nhất có thể.\n"
        "2. Gia tăng tỷ trọng khi đúng (có lãi).\n"
        "3. Cắt lỗ dứt khoát khi vi phạm quản trị rủi ro.\n"
        "4. Kích hoạt margin khi hội tụ đủ điều kiện.\n\n"
        "⚡ <b>CÁC LỆNH QUÉT TỨC THÌ (Bấm nút trên bàn phím điện thoại):</b>\n"
        "• 🏆 <b>Săn Siêu Cổ Nền 2 (No2)</b>: Truy lùng cổ phiếu đang nén chặt ở Nền số 2 (chưa bùng nổ)\n"
        "• 💎 <b>Radar Siêu Cổ Phiếu AI</b>: Sàng lọc Siêu Cổ Phiếu bằng mô hình ML 20 năm\n"
        "• ⚡ <b>Cổ phiếu giải phóng năng lượng</b>: Săn siêu cổ đạt Hạng A & Bùng nổ BMS\n"
        "• 🎯 <b>Kiểm tra Xung Lực BDI</b>: Đo lường xung lực BMS cho 2 danh mục hoặc gõ <i>'xung lực MÃ'</i>\n"
        "• 🌟 <b>Quét Pivot sàn HOSE</b>: Tìm điểm nổ bùng nổ Tầng 3\n"
        "• 🌱 <b>Quét Đẩy Nền tất cả</b>: Tìm điểm Pocket Pivot Tầng 2\n"
        "• 🔥 <b>Quét Nổ Vol Surge</b>: Săn siêu cổ đột biến thanh khoản ≥ 2.5x\n"
        "• 💼 <b>Xem Danh Mục Nắm Giữ</b>: Kiểm tra lãi/lỗ & cảnh báo kỷ luật RRBDI\n"
        "• 📡 <b>Xem Radar Watchlist</b>: Xem các mã đang săn đón\n\n"
        "💡 <i>Bạn chỉ cần bấm trực tiếp vào các nút trên bàn phím hoặc gõ tiếng Việt tự nhiên!</i>"
    )

def handle_telegram_command(raw_text: str, chat_id: str):
    text = (raw_text or "").strip().lower()
    
    # 000. CHIẾN LƯỢC SĂN SIÊU CỔ NỀN SỐ 2 (STRATEGY No2)
    if "no2" in text or "nền 2" in text or "nen 2" in text or "nền số 2" in text or "nen so 2" in text or "săn nền 2" in text or "san nen 2" in text or "/no2" in text:
        words = [w.strip().upper() for w in raw_text.replace(":", " ").replace(",", " ").replace("?", " ").replace("/", " ").split() if w.strip()]
        ignore_words = {"NO2", "NỀN", "NEN", "SỐ", "SO", "2", "SĂN", "SAN", "SIÊU", "SIEU", "CỔ", "CO", "PHIẾU", "PHIEU", "MÃ", "MA", "CHO", "CỦA", "CUA", "TẠI", "TAI"}
        potential_symbols = [w for w in words if 3 <= len(w) <= 4 and w.isalpha() and w not in ignore_words]
        if potential_symbols:
            target_sym = potential_symbols[0]
            send_telegram_alert(f"⏳ <i>Đang bóc tách 6 tầng Chiến Lược No2 cho cổ phiếu {target_sym}...</i>", chat_id_override=chat_id)
            msg, markup = format_no2_summary(target_sym)
            send_telegram_alert(msg, reply_markup=markup, chat_id_override=chat_id)
            return
        else:
            send_telegram_alert("⏳ <i>Đang quét Radar Săn Siêu Cổ Nền Số 2 (Strategy No2) toàn thị trường...</i>", chat_id_override=chat_id)
            msg, markup = format_no2_summary()
            send_telegram_alert(msg, reply_markup=markup, chat_id_override=chat_id)
            return

    # 00. RADAR SIÊU CỔ PHIẾU AI
    if "siêu cổ" in text or "sieu co" in text or "siêu cổ phiếu" in text or "sieu co phieu" in text or "super" in text or "radar siêu cổ" in text or "/super" in text:
        words = [w.strip().upper() for w in raw_text.replace(":", " ").replace(",", " ").replace("?", " ").split() if w.strip()]
        ignore_words = {"SIÊU", "SIEU", "CỔ", "CO", "PHIẾU", "PHIEU", "RADAR", "AI", "SUPER", "STOCK", "MÃ", "MA", "CHO", "CỦA", "CUA", "TẠI", "TAI"}
        potential_symbols = [w for w in words if 3 <= len(w) <= 4 and w.isalpha() and w not in ignore_words]
        if potential_symbols:
            target_sym = potential_symbols[0]
            send_telegram_alert(f"⏳ <i>Đang chạy mô hình AI phân tích Siêu Cổ Phiếu cho mã {target_sym}...</i>", chat_id_override=chat_id)
            msg = format_super_stock_summary(target_sym)
            send_telegram_alert(msg, chat_id_override=chat_id)
            return
        else:
            send_telegram_alert("⏳ <i>Đang quét Radar Siêu Cổ Phiếu AI trên toàn bộ dữ liệu 20 năm...</i>", chat_id_override=chat_id)
            msg = format_super_stock_summary()
            send_telegram_alert(msg, chat_id_override=chat_id)
            return

    # 0A. Cổ phiếu giải phóng năng lượng phiên hôm nay (Quét toàn thị trường + 2 danh mục)
    if "giải phóng năng lượng" in text or "giai phong nang luong" in text or "giải phóng" in text or "giai phong" in text or "năng lượng hôm nay" in text or "nang luong hom nay" in text or "/energy" in text:
        send_telegram_alert("⏳ <i>Đang rà soát toàn diện danh mục & thị trường tìm cổ phiếu GIẢI PHÓNG NĂNG LƯỢNG hôm nay... Vui lòng đợi vài giây!</i>", chat_id_override=chat_id)
        msg = format_market_energy_release_summary()
        send_telegram_alert(msg, chat_id_override=chat_id)
        return


    # 0B. Kiểm tra Xung Lực BDI (BMS)
    if "xung lực" in text or "xung luc" in text or "bms" in text or "chỉ số xung lực" in text or "kiểm tra xung lực" in text or "3p" in text or "15p" in text:
        words = [w.strip().upper() for w in raw_text.replace(":", " ").replace(",", " ").replace("?", " ").split() if w.strip()]
        ignore_words = {"BMS", "BDI", "CHO", "XUNG", "LỰC", "LUC", "XUN", "KIỂM", "TRA", "KIEM", "CHỈ", "SỐ", "CHI", "SO", "CỦA", "CUA", "MÃ", "MA", "CP", "TẠI", "TAI", "HOM", "NAY", "HÔM", "PHIEN", "PHIÊN"}
        potential_symbols = [w for w in words if 3 <= len(w) <= 4 and w.isalpha() and w not in ignore_words]
        
        if potential_symbols:
            target_sym = potential_symbols[0]
            send_telegram_alert(f"⏳ <i>Đang bóc tách 5 thước đo Xung Lực BDI (BMS) cho cổ phiếu {target_sym}...</i>", chat_id_override=chat_id)
            msg = format_single_stock_bms(target_sym)
            send_telegram_alert(msg, chat_id_override=chat_id)
            return
        else:
            send_telegram_alert("⏳ <i>Đang kiểm tra chỉ số Xung Lực BDI cho Danh mục nắm giữ & Watchlist...</i>", chat_id_override=chat_id)
            msg = format_portfolio_bms_summary()
            send_telegram_alert(msg, chat_id_override=chat_id)
            return

    # 1. Quét Pivot sàn HOSE
    if "pivot" in text:
        send_telegram_alert("⏳ <i>Đang rà soát toàn bộ sàn HOSE tìm điểm nổ Pivot Tầng 3... Vui lòng đợi vài giây!</i>", chat_id_override=chat_id)
        msg, btns = format_telegram_scan_result("PIVOT", force_refresh=True)
        markup = {"inline_keyboard": btns} if btns else None
        send_telegram_alert(msg, reply_markup=markup, chat_id_override=chat_id)
        return

    # 2. Quét Đẩy Nền (Pocket Pivot)
    if "đẩy nền" in text or "day nen" in text or "pocket" in text:
        send_telegram_alert("⏳ <i>Đang sàng lọc điểm đẩy nền Pocket Pivot Tầng 2... Vui lòng đợi vài giây!</i>", chat_id_override=chat_id)
        msg, btns = format_telegram_scan_result("DAYNEN", force_refresh=True)
        markup = {"inline_keyboard": btns} if btns else None
        send_telegram_alert(msg, reply_markup=markup, chat_id_override=chat_id)
        return

    # 3. Quét Điểm Cược sàn HOSE (C1)
    if "cược" in text or "cuoc" in text:
        send_telegram_alert("⏳ <i>Đang sàng lọc điểm cược cạn vol Tầng 1... Vui lòng đợi vài giây!</i>", chat_id_override=chat_id)
        msg, btns = format_telegram_scan_result("CUOC", force_refresh=True)
        markup = {"inline_keyboard": btns} if btns else None
        send_telegram_alert(msg, reply_markup=markup, chat_id_override=chat_id)
        return

    # 4. Quét Nổ Vol Surge (Đột biến thể tích)
    if "vol surge" in text or "nổ vol" in text or "no vol" in text or "đột biến" in text or "dot bien" in text or "/surge" in text:
        send_telegram_alert("⏳ <i>Đang rà soát nổ thanh khoản sớm (≥ 2.5x TB10)...</i>", chat_id_override=chat_id)
        msg, btns = format_telegram_scan_result("SURGE", force_refresh=True)
        markup = {"inline_keyboard": btns} if btns else None
        send_telegram_alert(msg, reply_markup=markup, chat_id_override=chat_id)
        return

    # 5. Quét tất cả / Lọc thị trường
    if "tất cả" in text or "tat ca" in text or "/all" in text:
        send_telegram_alert("⏳ <i>Đang tổng hợp cơ hội nổi bật ở cả 3 tầng điểm mua...</i>", chat_id_override=chat_id)
        msg, btns = format_telegram_scan_result("ALL", force_refresh=True)
        markup = {"inline_keyboard": btns} if btns else None
        send_telegram_alert(msg, reply_markup=markup, chat_id_override=chat_id)
        return

    # 6. Xem Danh Mục Nắm Giữ
    if "nắm giữ" in text or "nam giu" in text or "danh mục" in text or "danh muc" in text or "pnl" in text:
        msg = format_holdings_for_telegram()
        send_telegram_alert(msg, chat_id_override=chat_id)
        return

    # 7. Xem Radar Watchlist
    if "watchlist" in text or "radar" in text or "theo dõi" in text or "theo doi" in text:
        msg = format_watchlist_for_telegram()
        send_telegram_alert(msg, chat_id_override=chat_id)
        return

    # 8. Lệnh thêm thủ công mã vào radar: ví dụ "lưu SSI" hoặc "theo dõi SSI" hoặc "/radar SSI"
    if text.startswith("lưu ") or text.startswith("luu ") or text.startswith("/radar ") or text.startswith("/watch "):
        parts = raw_text.split()
        if len(parts) >= 2:
            sym = parts[1].upper().strip()
            res = save_watchlist_position(sym, "Thêm từ lệnh Telegram")
            send_telegram_alert(f"🎯 <b>{res.get('message', f'Đã lưu {sym} vào Watchlist!')}</b>\nBot sẽ tự động bám sát 30 phút/lần trong phiên để báo điểm nổ.", chat_id_override=chat_id)
            return

    # 9. Lệnh Start, Help hoặc mặc định
    send_telegram_alert(format_welcome_help(), chat_id_override=chat_id)

def handle_telegram_callback(token: str, cb_id: str, data: str, chat_id: str):
    if data.startswith("NO2_"):
        sym = data.replace("NO2_", "").strip().upper()
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                json={"callback_query_id": cb_id, "text": f"🏆 Đang bóc tách No2 cho {sym}..."},
                timeout=5
            )
        except Exception:
            pass
        msg, markup = format_no2_summary(sym)
        send_telegram_alert(msg, reply_markup=markup, chat_id_override=chat_id)
        return

    if data.startswith("WATCH_"):
        sym = data.replace("WATCH_", "").strip().upper()
        res = save_watchlist_position(sym, "Thêm từ Telegram Scanner")
        
        # Phản hồi popup nhanh trên màn hình điện thoại
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                json={"callback_query_id": cb_id, "text": f"✅ Đã thêm {sym} vào Radar!"},
                timeout=5
            )
        except Exception:
            pass
            
        send_telegram_alert(
            f"🎯 <b>ĐÃ ĐƯA {sym} VÀO RADAR THEO DÕI!</b>\n"
            f"• Tình trạng: Hệ thống đã ghi nhận {sym} vào Bảng 2 (Watchlist Radar).\n"
            f"• Cơ chế: Bot sẽ tự động quét 30 phút/lần trong phiên, phát tín hiệu bùng nổ Breakout gia tăng ngay khi xuất hiện!",
            chat_id_override=chat_id
        )

# =========================================================================
# 6. TIẾN TRÌNH LẮNG NGHE LỆNH TELEGRAM (LONG POLLING WORKER)
# =========================================================================
_POLLING_RUNNING = False

def start_telegram_polling_thread():
    """Khởi động luồng nền liên tục lắng nghe lệnh gửi từ Telegram (Long Polling)."""
    global _POLLING_RUNNING
    if _POLLING_RUNNING:
        return
    _POLLING_RUNNING = True
    
    t = threading.Thread(target=_polling_worker, daemon=True, name="TelegramPollingWorker")
    t.start()
    print("✅ Đã kích hoạt luồng lắng nghe lệnh Telegram (Long Polling) sẵn sàng!")

def _polling_worker():
    cfg = load_telegram_config()
    token = cfg.get("bot_token", "").strip()
    if not token:
        print("⚠️ Không có bot_token để chạy Polling.")
        return
        
    offset = None
    print("👂 Bot Telegram đang sẵn sàng lắng nghe mọi lệnh quét từ điện thoại của bạn...")
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"timeout": 20}
            if offset is not None:
                params["offset"] = offset
                
            resp = requests.get(url, params=params, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                updates = data.get("result", [])
                for u in updates:
                    offset = u["update_id"] + 1
                    
                    # 1. Nhận tin nhắn văn bản
                    if "message" in u:
                        msg = u["message"]
                        text = msg.get("text", "")
                        c_id = str(msg.get("chat", {}).get("id", ""))
                        if text and c_id:
                            print(f"[TELEGRAM COMMAND]: '{text}' từ chat {c_id}")
                            handle_telegram_command(text, c_id)
                            
                    # 2. Nhận tương tác nút bấm Inline
                    elif "callback_query" in u:
                        cb = u["callback_query"]
                        cb_id = cb.get("id", "")
                        data_val = cb.get("data", "")
                        c_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                        if cb_id and data_val and c_id:
                            print(f"[TELEGRAM CALLBACK]: '{data_val}' từ chat {c_id}")
                            handle_telegram_callback(token, cb_id, data_val, c_id)
            elif resp.status_code == 409:
                time.sleep(5)
            else:
                time.sleep(3)
        except Exception:
            time.sleep(3)

# =========================================================================
# 7. CHẾ ĐỘ DAEMON (CHẠY NGẦM LIÊN TỤC THEO ĐÚNG MỐC GIỜ YÊU CẦU)
# =========================================================================
def run_daemon_loop():
    """
    Vòng lặp chạy ngầm tự động điều phối:
    - Luôn lắng nghe lệnh từ điện thoại (Telegram Polling)
    - 2 DANH MỤC CÁ NHÂN (NẮM GIỮ & WATCHLIST):
      * 9h15 -> 14h30: Cứ 5 PHÚT quét Breakout 1 lần (RÚT NGẮN).
      * 13h01 -> 14h46: Cứ 3 PHÚT quét Xung Lực BMS (Giải phóng năng lượng) 1 lần (RÚT NGẮN).
    - TOÀN THỊ TRƯỜNG (GIỮ NGUYÊN LỊCH CỐ ĐỊNH):
      * 14h05: Quét phiên chiều toàn thị trường.
      * 14h30: Quét khẩn cấp trước ATC.
      * 15h02: Quét tổng kết EOD.
    """
    start_telegram_polling_thread()
    print("="*60)
    print("🤖 BOT RRBDI MONITOR ĐANG CHẠY NGẦM...")
    print(f"• [2 Danh mục] Quét Breakout trong phiên: Mỗi {INTERVAL_2_PORTFOLIOS_BREAKOUT // 60} phút (09:15 - 14:30)")
    print(f"• [2 Danh mục] Quét Xung Lực BMS:         Mỗi {INTERVAL_2_PORTFOLIOS_BMS // 60} phút (13:01 - 14:46)")
    print("• [Toàn thị trường] Quét phiên chiều:    14:05 (GIỮ NGUYÊN)")
    print("• [Toàn thị trường] Quét trước ATC:      14:30 (GIỮ NGUYÊN)")
    print("• [Toàn thị trường] Quét tổng kết EOD:   15:02 (GIỮ NGUYÊN)")
    print("="*60)
    
    last_breakout_scan = 0
    last_bms_scan = 0
    done_1405 = ""
    done_1430 = ""
    done_1502 = ""
    
    while True:
        now = datetime.now()
        cur_time_str = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")
        weekday = now.weekday() # 0 = Monday, 4 = Friday
        
        # Chỉ chạy Thứ 2 đến Thứ 6
        if weekday < 5:
            # 1. Quét Breakout cho 2 Danh mục mỗi 5 phút trong khung 09:15 - 14:30 (RÚT NGẮN)
            if dtime(9, 15) <= now.time() <= dtime(14, 30):
                if time.time() - last_breakout_scan >= INTERVAL_2_PORTFOLIOS_BREAKOUT: # 5 phút = 300s
                    scan_intraday_breakouts()
                    last_breakout_scan = time.time()
                    
            # 2. Quét Xung Lực BMS cho 2 Danh mục mỗi 3 phút trong khung 13:01 - 14:46 (RÚT NGẮN)
            if dtime(13, 1) <= now.time() <= dtime(14, 46):
                if time.time() - last_bms_scan >= INTERVAL_2_PORTFOLIOS_BMS: # 3 phút = 180s
                    scan_bms_momentum_alerts()
                    last_bms_scan = time.time()
                    
            # 3. Quét toàn thị trường lúc 14h05 (GIỮ NGUYÊN)
            if cur_time_str == "14:05" and done_1405 != today_str:
                scan_afternoon_14h()
                done_1405 = today_str
                
            # 4. Quét toàn thị trường lúc 14h30 (GIỮ NGUYÊN)
            if cur_time_str == "14:30" and done_1430 != today_str:
                scan_pre_atc_1430()
                done_1430 = today_str
                
            # 5. Quét toàn thị trường lúc 15h02 (GIỮ NGUYÊN)
            if cur_time_str == "15:02" and done_1502 != today_str:
                scan_eod_1502()
                done_1502 = today_str
                
        time.sleep(10) # Ngủ 10 giây để bắt chuẩn xác nhịp giờ

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RRBDI Telegram Monitor Bot")
    parser.add_argument("--mode", choices=["breakout", "bms", "afternoon", "pre_atc", "eod", "daemon", "test", "poll"], default="daemon",
                        help="Chế độ quét: breakout (5p cho 2 DM), bms (3p cho 2 DM từ 13h01-14h46), afternoon (14h05 TT), pre_atc (14h30 TT), eod (15h02 TT), daemon (tự động cả ngày), test (kiểm tra gửi tin), poll (chỉ lắng nghe lệnh từ điện thoại)")
    parser.add_argument("--force", action="store_true",
                        help="Bỏ qua kiểm tra giờ giao dịch và ngày cuối tuần (chạy cưỡng bức để kiểm tra/test)")
    args = parser.parse_args()
    
    if args.mode == "breakout":
        scan_intraday_breakouts(force=args.force)
    elif args.mode == "bms":
        scan_bms_momentum_alerts(force=args.force)
    elif args.mode == "afternoon":
        scan_afternoon_14h(force=args.force)
    elif args.mode == "pre_atc":
        scan_pre_atc_1430(force=args.force)
    elif args.mode == "eod":
        scan_eod_1502(force=args.force)
    elif args.mode == "test":
        print("Gửi tin nhắn thử nghiệm kiểm tra kết nối Telegram...")
        send_telegram_alert("🔔 <b>[VSA ĐẬU MẦM PRO]</b>: Kết nối Bot Telegram thành công! Hệ thống giám sát RRBDI đã sẵn sàng hoạt động.")
    elif args.mode == "poll":
        print("🤖 CHẾ ĐỘ LẮNG NGHE LỆNH TELEGRAM ĐANG HOẠT ĐỘNG...")
        send_telegram_alert("🚀 <b>[VSA ĐẬU MẦM PRO]</b>: Bot đã kích hoạt chế độ lắng nghe lệnh từ điện thoại! Hãy bấm nút trên bàn phím để quét.")
        _polling_worker()
    elif args.mode == "daemon":
        run_daemon_loop()
