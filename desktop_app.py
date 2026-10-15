import os
import sys
import time
import threading
import urllib.request
import multiprocessing

# 1. Prevent NoneType write errors in --windowed mode
class SafeStream:
    def __init__(self, log_path=None):
        self.log_path = log_path

    def write(self, s):
        if self.log_path:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(str(s))
            except Exception:
                pass

    def flush(self):
        pass

def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

log_dir = os.path.join(os.environ.get("LOCALAPPDATA", get_app_dir()), "VSA_DauMam_Pro")
try:
    os.makedirs(log_dir, exist_ok=True)
except Exception:
    pass

app_log_file = os.path.join(log_dir, "app.log")

if sys.stdout is None:
    sys.stdout = SafeStream(app_log_file)
if sys.stderr is None:
    sys.stderr = SafeStream(app_log_file)

def log_debug(msg):
    try:
        debug_file = os.path.join(get_app_dir(), "vsa_app.log")
        with open(debug_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def start_fastapi():
    try:
        import traceback
        import uvicorn
        from app import app
        config = uvicorn.Config(
            app=app,
            host="127.0.0.1",
            port=8000,
            log_level="error",
            access_log=False,
            log_config=None
        )
        server = uvicorn.Server(config)
        log_debug("FastAPI server starting on http://127.0.0.1:8000...")
        server.run()
    except Exception as e:
        import traceback
        err_msg = f"FastAPI Startup Error: {str(e)}\n{traceback.format_exc()}"
        log_debug(err_msg)
        try:
            with open(os.path.join(log_dir, "startup_error.log"), "a", encoding="utf-8") as f:
                f.write(err_msg + "\n")
        except Exception:
            pass

def wait_for_server(url, max_wait_sec=45):
    start_t = time.time()
    while time.time() - start_t < max_wait_sec:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VSA_Desktop_HealthCheck"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status in (200, 403):
                    return True
        except Exception:
            time.sleep(0.3)
    return False

if __name__ == "__main__":
    # Windows PyInstaller Freeze Support
    multiprocessing.freeze_support()

    try:
        import ctypes
        ctypes.windll.kernel32.AttachConsole(-1)
    except Exception:
        pass

    # CLI utility handlers for standalone executable
    if "--bot" in sys.argv:
        log_debug("Starting Bot Telegram daemon from CLI...")
        import bot_rrbdi_service
        bot_rrbdi_service.run_daemon_loop()
        sys.exit(0)

    if "--license-tool" in sys.argv or "--admin-license" in sys.argv:
        import admin_license_tool
        sys.argv = [arg for arg in sys.argv if arg not in ("--license-tool", "--admin-license")]
        if len(sys.argv) == 1:
            admin_license_tool.list_keys()
        else:
            import argparse
            parser = argparse.ArgumentParser(description="Admin License Tool")
            parser.add_argument("--create", action="store_true", help="Tạo key mới")
            parser.add_argument("--name", type=str, default="Khách Hàng VIP", help="Tên khách hàng")
            parser.add_argument("--days", type=int, default=30, help="Số ngày sử dụng (30, 90, 365, 3650)")
            parser.add_argument("--hwid", type=str, default="ANY", help="Mã máy tính (để ANY nếu gắn lần đầu)")
            parser.add_argument("--plan", type=str, default="VIP", help="Tên gói (VIP, MASTER, PRO)")
            parser.add_argument("--list", action="store_true", help="Xem danh sách key")
            args = parser.parse_args()
            if args.create:
                admin_license_tool.create_key(args.name, args.days, args.hwid, args.plan)
            elif args.list:
                admin_license_tool.list_keys()
        sys.exit(0)

    log_debug("=== Starting VSA Đậu Mầm Pro ===")
    target_url = "http://127.0.0.1:8000"

    # Check if server is already running on port 8000 (e.g. from previous instance)
    server_already_running = wait_for_server(f"{target_url}/api/license/hwid", max_wait_sec=3.0)

    if not server_already_running:
        server_thread = threading.Thread(target=start_fastapi, daemon=True)
        server_thread.start()
        server_ready = wait_for_server(f"{target_url}/api/license/hwid", max_wait_sec=45)
    else:
        log_debug("Server port 8000 already active, reusing existing instance.")
        server_ready = True

    if not server_ready:
        log_debug("Failed to connect to local server on port 8000!")
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "Không thể kết nối máy chủ phân tích nội bộ (Port 8000). Vui lòng kiểm tra lại ứng dụng.",
            "VSA Đậu Mầm Pro - Lỗi Khởi Động",
            0x10 # MB_ICONERROR
        )
        sys.exit(1)

    log_debug("Server is healthy and ready.")

    # Check command line flags: --browser or --server-only
    use_browser_only = "--browser" in sys.argv or "--server" in sys.argv

    if not use_browser_only:
        # Launch native Desktop Window using pywebview
        try:
            import webview
            log_debug("Opening pywebview native desktop window...")
            window = webview.create_window(
                title="VSA Đậu Mầm Pro — Hệ Thống VSA & Thuyết Đàn Sói",
                url=target_url,
                width=1320,
                height=860,
                min_size=(1024, 680)
            )
            t_start = time.time()
            webview.start()
            elapsed = time.time() - t_start
            log_debug(f"Webview closed after {elapsed:.2f}s")
            
            # If webview closed in under 2 seconds, it was likely headless or failed to render window
            if elapsed < 2.0:
                log_debug("Webview closed immediately (<2s), falling back to browser mode...")
                use_browser_only = True
            else:
                log_debug("App closed normally by user.")
                sys.exit(0)
        except Exception as e:
            log_debug(f"Native window failed: {e}. Switching to browser mode.")
            use_browser_only = True

    if use_browser_only:
        log_debug("Running in default browser mode...")
        import webbrowser
        webbrowser.open(target_url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log_debug("Exiting via KeyboardInterrupt.")
