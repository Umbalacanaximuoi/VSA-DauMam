import os
import sys
import time
import threading
import urllib.request
import subprocess

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

TARGET_URL = "http://127.0.0.1:8000/mobile"
SIMULATOR_URL = "http://127.0.0.1:8000/simulator"

def is_server_ready(url, timeout=1.0):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VSA_Mobile_Simulator_Check"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 403)
    except Exception:
        return False

def start_fastapi_server():
    import uvicorn
    from app import app
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=8000,
        log_level="error",
        access_log=False
    )
    server = uvicorn.Server(config)
    server.run()

def launch_phone_window():
    print("=" * 60)
    print("📱 VSA ĐẬU MẦM PRO — KHỞI ĐỘNG GIẢ LẬP ĐIỆN THOẠI DESKTOP")
    print("=" * 60)

    # 1. Kiểm tra máy chủ port 8000
    if not is_server_ready("http://127.0.0.1:8000/mobile"):
        print("⏳ Đang khởi động máy chủ phân tích FastAPI nội bộ...")
        t = threading.Thread(target=start_fastapi_server, daemon=True)
        t.start()

        waited = 0
        while waited < 30:
            if is_server_ready("http://127.0.0.1:8000/mobile"):
                break
            time.sleep(0.5)
            waited += 0.5
        
        if waited >= 30:
            print("❌ Không thể kết nối máy chủ nội bộ trên cổng 8000.")
            sys.exit(1)

    print("✅ Máy chủ phân tích đã sẵn sàng tại http://127.0.0.1:8000")
    print("📱 Đang mở cửa sổ giả lập tỉ lệ chuẩn điện thoại (430 x 900)...")

    # 2. Ưu tiên 1: Chạy bằng PyWebView Native Window
    launched = False
    try:
        import webview
        print("🚀 Khởi chạy cửa sổ Native Webview (Tỉ lệ chuẩn iPhone)...")
        window = webview.create_window(
            title="📱 VSA Đậu Mầm Pro — Mobile Simulator (iPhone 16 Pro Max)",
            url=TARGET_URL,
            width=430,
            height=900,
            resizable=True,
            min_size=(375, 667)
        )
        webview.start()
        launched = True
    except Exception as e:
        print(f"⚠️ PyWebView không khả dụng: {e}. Chuyển sang trình duyệt App Mode...")

    # 3. Ưu tiên 2: Chạy bằng Edge / Chrome App Mode (Borderless Phone Window)
    if not launched:
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if os.path.exists(edge_path):
            print("🚀 Mở cửa sổ Standalone App Mode qua Microsoft Edge...")
            cmd = f'"{edge_path}" --app={TARGET_URL} --window-size=430,900'
            subprocess.Popen(cmd, shell=True)
            launched = True
        else:
            import webbrowser
            print("🚀 Mở trên trình duyệt mặc định với khung mô phỏng Studio...")
            webbrowser.open(SIMULATOR_URL)

    print("✨ Hoàn tất! Bạn có thể thao tác trực tiếp trên giao diện giả lập.")

if __name__ == "__main__":
    launch_phone_window()
