import os
import sys
import json
import base64
import hmac
import hashlib
import time
import subprocess
from datetime import datetime, timezone, timedelta
import urllib.request
from typing import Optional, List, Dict, Any

MASTER_SECRET_KEY = b"DAU_MAM_PRO_VSA_ZERO_LOSS_SECRET_2026_@#$!"
ADMIN_SECRET_KEY = b"ADMIN_SECRET_MASTER_TOKEN_2026_@#$!"
DEFAULT_ADMIN_PASSWORD = "daumam2026@admin"

LICENSE_DIR = os.path.join(os.path.expanduser("~"), ".vsa_daumam")
LICENSE_FILE = os.path.join(LICENSE_DIR, "license.json")
REGISTRY_FILE = os.path.join(LICENSE_DIR, "registry.json")
TAMPER_FILE = os.path.join(LICENSE_DIR, ".state.dat")

os.makedirs(LICENSE_DIR, exist_ok=True)

def get_hardware_id() -> str:
    """Generates a unique, stable Hardware ID (HWID)."""
    hw_components = []
    if sys.platform.startswith("win"):
        try:
            out = subprocess.check_output("wmic csproduct get uuid", shell=True, text=True, stderr=subprocess.DEVNULL)
            lines = [l.strip() for l in out.splitlines() if l.strip() and "UUID" not in l.upper()]
            if lines:
                hw_components.append(lines[0])
        except Exception:
            pass

        try:
            out = subprocess.check_output("wmic cpu get processorid", shell=True, text=True, stderr=subprocess.DEVNULL)
            lines = [l.strip() for l in out.splitlines() if l.strip() and "PROCESSORID" not in l.upper()]
            if lines:
                hw_components.append(lines[0])
        except Exception:
            pass
            
        try:
            out = subprocess.check_output("wmic os get serialnumber", shell=True, text=True, stderr=subprocess.DEVNULL)
            lines = [l.strip() for l in out.splitlines() if l.strip() and "SERIALNUMBER" not in l.upper()]
            if lines:
                hw_components.append(lines[0])
        except Exception:
            pass
    
    if not hw_components:
        import uuid
        hw_components.append(str(uuid.getnode()))

    raw_str = "|".join(hw_components)
    raw_hash = hashlib.sha256(raw_str.encode('utf-8')).hexdigest().upper()
    formatted_hwid = f"DM-{raw_hash[0:4]}-{raw_hash[4:8]}-{raw_hash[8:12]}-{raw_hash[12:16]}"
    return formatted_hwid

def get_trusted_internet_time() -> datetime:
    """Fetches atomic clock time from trusted servers with rollback tamper detection."""
    vn_tz = timezone(timedelta(hours=7))
    trusted_dt = None
    
    time_servers = [
        "https://www.google.com",
        "https://www.cloudflare.com",
        "https://vnstocks.com"
    ]
    
    for url in time_servers:
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "VSA-DauMam-Verifier/1.0"})
            with urllib.request.urlopen(req, timeout=2.5) as response:
                date_header = response.headers.get("Date")
                if date_header:
                    import email.utils
                    parsed_tuple = email.utils.parsedate_to_datetime(date_header)
                    trusted_dt = parsed_tuple.astimezone(vn_tz)
                    break
        except Exception:
            continue
            
    if trusted_dt is None:
        local_dt = datetime.now(vn_tz)
        trusted_dt = local_dt

    _check_and_update_tamper_state(trusted_dt)
    return trusted_dt

def _check_and_update_tamper_state(current_dt: datetime):
    try:
        curr_ts = int(current_dt.timestamp())
        if os.path.exists(TAMPER_FILE):
            with open(TAMPER_FILE, "r", encoding="utf-8") as f:
                saved_data = f.read().strip()
                if saved_data:
                    parts = saved_data.split(":")
                    if len(parts) == 2:
                        last_ts = int(parts[0])
                        expected_hash = hashlib.sha256(f"{last_ts}:TAMPER_SALT".encode()).hexdigest()
                        if parts[1] == expected_hash and curr_ts < (last_ts - 3600):
                            raise PermissionError("CLOCK_TAMPERED: System clock has been rolled back.")
        
        new_hash = hashlib.sha256(f"{curr_ts}:TAMPER_SALT".encode()).hexdigest()
        with open(TAMPER_FILE, "w", encoding="utf-8") as f:
            f.write(f"{curr_ts}:{new_hash}")
    except PermissionError:
        raise
    except Exception:
        pass

# ==================== LICENSE REGISTRY & DATABASE ====================

def _load_registry() -> Dict[str, Any]:
    if not os.path.exists(REGISTRY_FILE):
        # Initialize default seed registry
        curr_hwid = get_hardware_id()
        vn_tz = timezone(timedelta(hours=7))
        now = datetime.now(vn_tz)
        expires_dt = now.replace(year=now.year + 50)
        
        # Seed VIP Lifetime for current dev machine
        seed_key = generate_license_key("Admin VSA Pro", 18262, curr_hwid, "VIP_LIFETIME")
        initial_data = {
            seed_key: {
                "client": "Admin VSA Pro",
                "license_key": seed_key,
                "bound_hwid": curr_hwid,
                "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": expires_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "plan": "VIP_LIFETIME",
                "days_initial": 18262,
                "status": "ACTIVE",
                "notes": "Bản quyền quản trị viên VIP Vĩnh Viễn",
                "last_active_at": now.strftime("%Y-%m-%d %H:%M:%S")
            }
        }
        _save_registry(initial_data)
        return initial_data

    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_registry(registry: Dict[str, Any]):
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

def generate_license_key(client_name: str, days: int, bound_hwid: str = "ANY", plan_name: str = "VIP") -> str:
    vn_tz = timezone(timedelta(hours=7))
    now = datetime.now(vn_tz)
    
    if days >= 3650:
        expires_dt = now.replace(year=now.year + 50)
        plan_code = "VIP_LIFETIME"
    else:
        expires_dt = now + timedelta(days=days)
        plan_code = f"{plan_name}_{days}D"

    payload = {
        "client": client_name.strip(),
        "created_at": now.strftime("%Y-%m-%d"),
        "expires_at": expires_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "bound_hwid": bound_hwid.strip().upper(),
        "plan": plan_code
    }
    
    payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8').rstrip('=')
    signature = hmac.new(MASTER_SECRET_KEY, payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()[:16].upper()
    license_key = f"DMVIP-{payload_b64}-{signature}"
    return license_key

def parse_and_validate_key(license_key: str, current_hwid: str = None) -> dict:
    if not license_key or not license_key.startswith("DMVIP-"):
        return {"valid": False, "status": "INVALID_FORMAT", "message": "Mã bản quyền không đúng định dạng."}
        
    parts = license_key.split("-")
    if len(parts) != 3:
        return {"valid": False, "status": "INVALID_FORMAT", "message": "Mã bản quyền không hợp lệ."}
        
    payload_b64 = parts[1]
    provided_sig = parts[2].upper()
    
    expected_sig = hmac.new(MASTER_SECRET_KEY, payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()[:16].upper()
    if not hmac.compare_digest(provided_sig, expected_sig):
        return {"valid": False, "status": "INVALID_SIGNATURE", "message": "Chữ ký bản quyền không hợp lệ hoặc đã bị can thiệp."}
        
    try:
        padded_b64 = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_json = base64.urlsafe_b64decode(padded_b64.encode('utf-8')).decode('utf-8')
        payload = json.loads(payload_json)
    except Exception as e:
        return {"valid": False, "status": "CORRUPT_PAYLOAD", "message": f"Không thể giải mã dữ liệu: {e}"}

    curr_hw = (current_hwid or get_hardware_id()).upper()
    bound_hw = payload.get("bound_hwid", "ANY").upper()
    
    if bound_hw != "ANY" and bound_hw != curr_hw:
        return {
            "valid": False,
            "status": "INVALID_HWID",
            "message": f"Mã bản quyền này được cấp cho máy khác ({bound_hw}). Máy hiện tại: ({curr_hw}).",
            "payload": payload
        }
        
    return {"valid": True, "payload": payload}

def activate_license(license_key: str) -> dict:
    curr_hwid = get_hardware_id()
    val_res = parse_and_validate_key(license_key, curr_hwid)
    if not val_res["valid"]:
        return val_res
        
    payload = val_res["payload"]
    if payload.get("bound_hwid") == "ANY":
        payload["bound_hwid"] = curr_hwid
        
    license_data = {
        "license_key": license_key,
        "activated_at": datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S"),
        "bound_hwid": curr_hwid,
        "payload": payload
    }
    
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        json.dump(license_data, f, indent=2, ensure_ascii=False)
        
    # Also record in registry if not present
    registry = _load_registry()
    if license_key not in registry:
        registry[license_key] = {
            "client": payload.get("client", "Khách hàng"),
            "license_key": license_key,
            "bound_hwid": curr_hwid,
            "created_at": payload.get("created_at", datetime.now().strftime("%Y-%m-%d")),
            "expires_at": payload.get("expires_at"),
            "plan": payload.get("plan", "VIP"),
            "status": "ACTIVE",
            "last_active_at": datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S")
        }
        _save_registry(registry)
        
    return verify_license_status()

def reset_local_license() -> dict:
    """Xóa file license.json cục bộ để đưa máy về trạng thái Gatekeeper ban đầu (dùng cho test/chuyển tài khoản)."""
    if os.path.exists(LICENSE_FILE):
        try:
            os.remove(LICENSE_FILE)
        except Exception:
            pass
    return verify_license_status()

def verify_license_status() -> dict:
    curr_hwid = get_hardware_id()
    
    if not os.path.exists(LICENSE_FILE):
        return {
            "valid": False,
            "status": "NOT_ACTIVATED",
            "message": "Phần mềm chưa được kích hoạt bản quyền. Vui lòng nhập License Key từ Admin.",
            "hwid": curr_hwid,
            "days_left": 0
        }
        
    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        license_key = data.get("license_key", "")
        val_res = parse_and_validate_key(license_key, curr_hwid)
        if not val_res["valid"]:
            return {
                "valid": False,
                "status": val_res["status"],
                "message": val_res["message"],
                "hwid": curr_hwid,
                "days_left": 0
            }
            
        payload = val_res["payload"]
        
        # Check against Registry for Remote Revocation or Remote Renewal
        registry = _load_registry()
        reg_entry = registry.get(license_key)
        if reg_entry:
            # Remote Revocation Check
            if reg_entry.get("status") == "REVOKED":
                return {
                    "valid": False,
                    "status": "REVOKED",
                    "message": "⛔ Bản quyền của bạn đã bị KHÓA từ máy chủ quản trị. Vui lòng liên hệ Admin để mở lại.",
                    "client": payload.get("client"),
                    "plan": payload.get("plan"),
                    "hwid": curr_hwid,
                    "days_left": 0
                }
                
            # Remote Renewal Sync (if admin extended expires_at in registry)
            reg_expires = reg_entry.get("expires_at")
            if reg_expires and reg_expires != payload.get("expires_at"):
                payload["expires_at"] = reg_expires
                data["payload"] = payload
                with open(LICENSE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    
            # Update last active timestamp
            reg_entry["last_active_at"] = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S")
            _save_registry(registry)
        
        try:
            trusted_now = get_trusted_internet_time()
        except PermissionError:
            return {
                "valid": False,
                "status": "CLOCK_TAMPERED",
                "message": "Phát hiện can thiệp lùi ngày giờ hệ thống máy tính. Vui lòng chỉnh lại ngày giờ chuẩn.",
                "hwid": curr_hwid,
                "days_left": 0
            }
            
        vn_tz = timezone(timedelta(hours=7))
        expires_str = payload.get("expires_at", "2000-01-01 00:00:00")
        expires_dt = datetime.strptime(expires_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=vn_tz)
        
        diff = expires_dt - trusted_now
        total_seconds = diff.total_seconds()
        days_left = max(0, int(total_seconds // 86400))
        hours_left = max(0, int((total_seconds % 86400) // 3600))
        
        if total_seconds <= 0:
            if reg_entry:
                reg_entry["status"] = "EXPIRED"
                _save_registry(registry)
            return {
                "valid": False,
                "status": "EXPIRED",
                "message": f"Bản quyền đã hết hạn vào ngày {expires_str}.",
                "client": payload.get("client"),
                "plan": payload.get("plan"),
                "expired_at": expires_str,
                "hwid": curr_hwid,
                "days_left": 0
            }
            
        return {
            "valid": True,
            "status": "ACTIVE",
            "message": f"Bản quyền VIP đang hoạt động. Còn {days_left} ngày.",
            "client": payload.get("client"),
            "plan": payload.get("plan"),
            "expired_at": expires_str,
            "days_left": days_left,
            "hours_left": hours_left,
            "hwid": curr_hwid,
            "trusted_time": trusted_now.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return {
            "valid": False,
            "status": "ERROR",
            "message": f"Lỗi kiểm tra bản quyền: {e}",
            "hwid": curr_hwid,
            "days_left": 0
        }

# ==================== ADMIN MANAGEMENT FUNCTIONS ====================

def verify_admin_token(token: str) -> bool:
    if not token:
        return False
    # Check if raw token matches default password or matches HMAC hash
    if token == DEFAULT_ADMIN_PASSWORD:
        return True
    expected_token = hashlib.sha256(f"{DEFAULT_ADMIN_PASSWORD}:ADMIN_SALT".encode()).hexdigest()
    return hmac.compare_digest(token, expected_token)

def admin_login(password: str) -> dict:
    if password == DEFAULT_ADMIN_PASSWORD:
        token = hashlib.sha256(f"{DEFAULT_ADMIN_PASSWORD}:ADMIN_SALT".encode()).hexdigest()
        return {"success": True, "token": token, "message": "Đăng nhập Quản Trị Viên thành công!"}
    return {"success": False, "message": "Mật khẩu Quản Trị Viên không chính xác!"}

def admin_list_licenses() -> dict:
    registry = _load_registry()
    vn_tz = timezone(timedelta(hours=7))
    now = datetime.now(vn_tz)
    
    licenses_list = []
    active_count = 0
    expiring_soon_count = 0
    expired_count = 0
    revoked_count = 0
    
    for key, item in registry.items():
        expires_str = item.get("expires_at", "2000-01-01 00:00:00")
        try:
            exp_dt = datetime.strptime(expires_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=vn_tz)
            diff = (exp_dt - now).total_seconds()
            days_left = max(0, int(diff // 86400))
        except Exception:
            days_left = 0
            
        status = item.get("status", "ACTIVE")
        if status != "REVOKED":
            if days_left <= 0:
                status = "EXPIRED"
            else:
                status = "ACTIVE"
                
        if status == "ACTIVE":
            active_count += 1
            if days_left <= 7:
                expiring_soon_count += 1
        elif status == "EXPIRED":
            expired_count += 1
        elif status == "REVOKED":
            revoked_count += 1
            
        licenses_list.append({
            "client": item.get("client", "Khách hàng"),
            "license_key": key,
            "bound_hwid": item.get("bound_hwid", "ANY"),
            "created_at": item.get("created_at", "--"),
            "expires_at": expires_str,
            "days_left": days_left,
            "plan": item.get("plan", "VIP"),
            "status": status,
            "last_active_at": item.get("last_active_at", "--"),
            "notes": item.get("notes", "")
        })
        
    licenses_list.sort(key=lambda x: (0 if x["status"] == "ACTIVE" else 1, x["days_left"]))
    
    return {
        "status": "success",
        "stats": {
            "total": len(licenses_list),
            "active": active_count,
            "expiring_soon": expiring_soon_count,
            "expired": expired_count,
            "revoked": revoked_count
        },
        "licenses": licenses_list
    }

def admin_create_license(client_name: str, days: int, bound_hwid: str = "ANY", plan_name: str = "VIP", notes: str = "") -> dict:
    client_name = client_name.strip()
    if not client_name:
        return {"success": False, "message": "Tên khách hàng không được để trống!"}
        
    license_key = generate_license_key(client_name, days, bound_hwid, plan_name)
    val_res = parse_and_validate_key(license_key, bound_hwid if bound_hwid != "ANY" else None)
    if not val_res["valid"]:
        return {"success": False, "message": "Lỗi khi sinh mã bản quyền."}
        
    payload = val_res["payload"]
    registry = _load_registry()
    
    registry[license_key] = {
        "client": client_name,
        "license_key": license_key,
        "bound_hwid": bound_hwid.strip().upper(),
        "created_at": payload.get("created_at", datetime.now().strftime("%Y-%m-%d")),
        "expires_at": payload.get("expires_at"),
        "plan": payload.get("plan", plan_name),
        "days_initial": days,
        "status": "ACTIVE",
        "notes": notes,
        "last_active_at": "--"
    }
    _save_registry(registry)
    
    return {
        "success": True,
        "message": f"Tạo License Key thành công cho {client_name} ({days} ngày)!",
        "license_key": license_key,
        "client": client_name,
        "expires_at": payload.get("expires_at"),
        "bound_hwid": bound_hwid
    }

def admin_renew_license(license_key: str, extra_days: int) -> dict:
    registry = _load_registry()
    if license_key not in registry:
        return {"success": False, "message": "Không tìm thấy License Key này trong cơ sở dữ liệu."}
        
    item = registry[license_key]
    vn_tz = timezone(timedelta(hours=7))
    now = datetime.now(vn_tz)
    
    current_expires_str = item.get("expires_at")
    try:
        current_exp_dt = datetime.strptime(current_expires_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=vn_tz)
        base_dt = max(now, current_exp_dt)
    except Exception:
        base_dt = now
        
    new_exp_dt = base_dt + timedelta(days=extra_days)
    new_expires_str = new_exp_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    item["expires_at"] = new_expires_str
    item["status"] = "ACTIVE"
    _save_registry(registry)
    
    # If the current machine is using this license, update local license.json immediately
    if os.path.exists(LICENSE_FILE):
        try:
            with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                loc_data = json.load(f)
            if loc_data.get("license_key") == license_key:
                loc_data["payload"]["expires_at"] = new_expires_str
                with open(LICENSE_FILE, "w", encoding="utf-8") as f:
                    json.dump(loc_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
            
    return {
        "success": True,
        "message": f"Gia hạn thành công thêm {extra_days} ngày cho {item.get('client')} (Hết hạn: {new_expires_str}).",
        "new_expires_at": new_expires_str
    }

def admin_revoke_license(license_key: str) -> dict:
    registry = _load_registry()
    if license_key not in registry:
        return {"success": False, "message": "Không tìm thấy License Key!"}
        
    registry[license_key]["status"] = "REVOKED"
    _save_registry(registry)
    return {"success": True, "message": f"Đã KHÓA bản quyền của {registry[license_key].get('client')} thành công!"}

def admin_unrevoke_license(license_key: str) -> dict:
    registry = _load_registry()
    if license_key not in registry:
        return {"success": False, "message": "Không tìm thấy License Key!"}
        
    registry[license_key]["status"] = "ACTIVE"
    _save_registry(registry)
    return {"success": True, "message": f"Đã MỞ KHÓA bản quyền cho {registry[license_key].get('client')} thành công!"}

def admin_delete_license(license_key: str) -> dict:
    registry = _load_registry()
    if license_key in registry:
        client = registry[license_key].get("client")
        del registry[license_key]
        _save_registry(registry)
        return {"success": True, "message": f"Đã xóa bản quyền của {client} khỏi hệ thống."}
    return {"success": False, "message": "Không tìm thấy License Key cần xóa."}

def admin_get_expiring_warnings(threshold_days: int = 7) -> dict:
    reg_data = admin_list_licenses()
    expiring_clients = []
    
    for lic in reg_data["licenses"]:
        if lic["status"] == "ACTIVE" and lic["days_left"] <= threshold_days:
            msg_template = (
                f"🌱 [VSA ĐẬU MẦM PRO] Thông báo gia hạn bản quyền:\n"
                f"Kính chào Anh/Chị {lic['client']},\n"
                f"Gói bản quyền {lic['plan']} của Anh/Chị sẽ hết hạn vào ngày {lic['expires_at']} (Còn {lic['days_left']} ngày).\n"
                f"Để không bị gián đoạn phân tích VSA và quét 3 Tầng Nền, Anh/Chị vui lòng liên hệ Admin để gia hạn nhé!"
            )
            expiring_clients.append({
                "client": lic["client"],
                "license_key": lic["license_key"],
                "bound_hwid": lic["bound_hwid"],
                "days_left": lic["days_left"],
                "expires_at": lic["expires_at"],
                "message_template": msg_template
            })
            
    return {
        "status": "success",
        "threshold_days": threshold_days,
        "count": len(expiring_clients),
        "clients": expiring_clients
    }
