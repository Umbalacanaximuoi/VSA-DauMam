import os
import sys
import json
import argparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from license_manager import generate_license_key, parse_and_validate_key, get_hardware_id

DB_FILE = os.path.join(os.path.dirname(__file__), "client_licenses_db.json")

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def create_key(client_name, days, bound_hwid="ANY", plan_name="VIP"):
    key = generate_license_key(client_name, days, bound_hwid, plan_name)
    val = parse_and_validate_key(key)
    
    record = {
        "client": client_name,
        "plan": val["payload"]["plan"],
        "days": days,
        "created_at": val["payload"]["created_at"],
        "expires_at": val["payload"]["expires_at"],
        "bound_hwid": bound_hwid,
        "license_key": key
    }
    
    db = load_db()
    db.append(record)
    save_db(db)
    
    print("="*70)
    print("✅ ĐÃ TẠO BẢN QUYỀN MỚI THÀNH CÔNG!")
    print("="*70)
    print(f"👤 Khách hàng: {client_name}")
    print(f"📦 Gói:        {record['plan']} ({days} ngày)")
    print(f"⏳ Hết hạn:    {record['expires_at']}")
    print(f"💻 Gắn mã máy: {bound_hwid}")
    print(f"🔑 LICENSE KEY (Gửi chuỗi này cho khách hàng):")
    print(f"\n   {key}\n")
    print("="*70)
    return key

def list_keys():
    db = load_db()
    print("="*80)
    print(f"📋 DANH SÁCH BẢN QUYỀN ĐÃ CẤP ({len(db)} khách hàng)")
    print("="*80)
    if not db:
        print("  (Chưa có bản quyền nào được tạo)")
        return
    for idx, r in enumerate(db, 1):
        print(f"{idx}. [{r.get('plan')}] {r.get('client')} | Hết hạn: {r.get('expires_at')} | Máy: {r.get('bound_hwid')}")
        print(f"   Key: {r.get('license_key')}\n")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("🛠️ CÔNG CỤ TẠO BẢN QUYỀN ADMIN — VSA ĐẬU MẦM PRO")
        print("Cách dùng:")
        print("  python admin_license_tool.py --create --name \"Nguyễn Văn A\" --days 30")
        print("  python admin_license_tool.py --create --name \"VIP Member\" --days 3650  (Vĩnh viễn)")
        print("  python admin_license_tool.py --list")
        sys.exit(0)
        
    parser = argparse.ArgumentParser(description="Admin License Tool")
    parser.add_argument("--create", action="store_true", help="Tạo key mới")
    parser.add_argument("--name", type=str, default="Khách Hàng VIP", help="Tên khách hàng")
    parser.add_argument("--days", type=int, default=30, help="Số ngày sử dụng (30, 90, 365, 3650)")
    parser.add_argument("--hwid", type=str, default="ANY", help="Mã máy tính (để ANY nếu gắn lần đầu)")
    parser.add_argument("--plan", type=str, default="VIP", help="Tên gói (VIP, MASTER, PRO)")
    parser.add_argument("--list", action="store_true", help="Xem danh sách key")
    
    args = parser.parse_args()
    if args.create:
        create_key(args.name, args.days, args.hwid, args.plan)
    elif args.list:
        list_keys()
