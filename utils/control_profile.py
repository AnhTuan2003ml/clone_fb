"""
CDP Profile Controller - Điều khiển Chrome qua DevTools Protocol
Hỗ trợ đa phiên, xóa lịch sử profile, và quản lý vòng đời browser.
"""

import subprocess
import time
import shutil
import tempfile
import os
import json
import socket
from typing import Optional, Dict, List, Callable
import requests
import threading
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor


@dataclass
class CDPSession:
    """Đại diện cho một phiên CDP"""
    session_id: str
    port: int
    profile_dir: str
    process: Optional[subprocess.Popen] = None
    is_active: bool = False
    created_at: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()


class MasterProfileController:
    """
    Controller để điều khiển Chrome master profile qua CDP.
    
    Features:
    - Khởi động Chrome với CDP trên port chỉ định
    - Tự động copy master profile -> temp profile cho mỗi phiên
    - Xóa lịch sử profile mỗi khi được gọi
    - Hỗ trợ đa phiên (mỗi phiên = 1 port + 1 temp profile riêng)
    - Cleanup tự động khi phiên kết thúc
    """
    
    def __init__(
        self,
        master_profile_path: str = "master",
        chrome_path: Optional[str] = None,
        base_port: int = 9222
    ):
        """
        Args:
            master_profile_path: Đường dẫn đến master profile
            chrome_path: Đường dẫn đến Chrome executable (auto-detect nếu None)
            base_port: Port bắt đầu cho CDP
        """
        self.master_profile = os.path.abspath(master_profile_path)
        self.chrome_path = chrome_path or self._find_chrome()
        self.base_port = base_port
        self.sessions: Dict[str, CDPSession] = {}
        self._lock = threading.Lock()
        self._port_lock = threading.Lock()
        self._used_ports: set = set()
        
    def _find_chrome(self) -> str:
        """Tự động tìm Chrome executable"""
        possible_paths = [
            # Windows
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            # macOS
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            # Linux
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # Thử tìm trong PATH
        for cmd in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
            try:
                result = subprocess.run(
                    ["where" if os.name == "nt" else "which", cmd],
                    capture_output=True,
                    text=True,
                    check=True
                )
                return result.stdout.strip().split("\n")[0]
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        raise RuntimeError("Không tìm thấy Chrome. Vui lòng cung cấp chrome_path.")
    
    def _get_available_port(self) -> int:
        """Tìm port trống chưa được sử dụng"""
        with self._port_lock:
            port = self.base_port
            while port in self._used_ports or not self._is_port_available(port):
                port += 1
            self._used_ports.add(port)
            return port
    
    def _is_port_available(self, port: int) -> bool:
        """Kiểm tra xem port có đang được sử dụng không"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                return result != 0  # 0 = port đang được sử dụng
        except Exception:
            return False
    
    def _copy_master_profile(self, session_id: str) -> str:
        """
        Copy master profile sang thư mục tạm cho phiên mới.
        Xóa lịch sử trong quá trình copy.
        """
        temp_dir = tempfile.mkdtemp(prefix=f"cdp_profile_{session_id}_")
        
        print(f"[{session_id}] Copying master profile từ {self.master_profile}...")
        
        # Copy toàn bộ master profile
        shutil.copytree(
            self.master_profile,
            temp_dir,
            symlinks=False,
            ignore_dangling_symlinks=True,
            dirs_exist_ok=True
        )
        
        # Xóa lịch sử trong profile vừa copy
        self._clear_profile_history(temp_dir, session_id)
        
        return temp_dir
    
    def _clear_profile_history(self, profile_dir: str, session_id: str):
        """
        Xóa lịch sử trong profile directory.
        Giữ lại Extensions và các dữ liệu quan trọng.
        """
        print(f"[{session_id}] Đang xóa lịch sử profile...")
        
        default_dir = os.path.join(profile_dir, "Default")
        if not os.path.isdir(default_dir):
            print(f"[{session_id}] Không tìm thấy thư mục Default")
            return
        
        # Các thư mục/file cần giữ lại
        keep_items = {
            "Extensions",
            "Local Extension Settings",
            "Extension Rules",
            "Extension State",
            "Managed Extension Settings",
        }
        
        # Các file/thư mục cần xóa (lịch sử, cookies, session)
        history_targets = {
            # Cookies & Auth
            "Cookies", "Cookies-journal",
            "Login Data", "Login Data-journal",
            "Login Data For Account", "Login Data For Account-journal",
            # Session
            "Current Session", "Current Tabs",
            "Last Session", "Last Tabs",
            # History & Navigation
            "History", "History-journal",
            "Visited Links",
            "Top Sites", "Top Sites-journal",
            "Network Action Predictor", "Network Action Predictor-journal",
            # Web Data
            "Web Data", "Web Data-journal",
            "Favicons", "Favicons-journal",
            # Storage
            "Local Storage",
            "Session Storage",
            "IndexedDB",
            "databases",
            "blob_storage",
            "Service Worker",
            "shared_proto_db",
            # Cache
            "Cache", "Code Cache", "GPUCache",
            # Misc
            "QuotaManager", "QuotaManager-journal",
            "TransportSecurity", "TransportSecurity-journal",
            "Extension Cookies", "Extension Cookies-journal",
            "Platform Notifications",
            "GCM Store",
            "AutofillStrikeDatabase",
            # Network & Security
            "Network Persistent State",
            "Reporting and NEL",
            "Reporting and NEL-journal",
        }
        
        deleted_count = 0
        for item in os.listdir(default_dir):
            if item in keep_items:
                print(f"[{session_id}]   Giữ lại: {item}")
                continue
                
            full_path = os.path.join(default_dir, item)
            
            # Xóa nếu là file/thư mục lịch sử
            if item in history_targets or item.endswith(('-journal', '.log')):
                try:
                    if os.path.isfile(full_path) or os.path.islink(full_path):
                        os.remove(full_path)
                        deleted_count += 1
                    elif os.path.isdir(full_path):
                        shutil.rmtree(full_path, ignore_errors=True)
                        deleted_count += 1
                except Exception as e:
                    print(f"[{session_id}]   Lỗi xóa {item}: {e}")
        
        print(f"[{session_id}] Đã xóa {deleted_count} mục lịch sử.")
    
    def start_session(
        self,
        session_id: Optional[str] = None,
        custom_port: Optional[int] = None,
        headless: bool = False,
        extra_args: Optional[List[str]] = None
    ) -> CDPSession:
        """
        Khởi động một phiên CDP mới.
        
        Args:
            session_id: ID cho phiên (auto-generate nếu None)
            custom_port: Port cụ thể (auto-assign nếu None)
            headless: Chạy headless mode
            extra_args: Thêm arguments cho Chrome
            
        Returns:
            CDPSession object
        """
        with self._lock:
            session_id = session_id or f"session_{int(time.time() * 1000)}"
            
            if session_id in self.sessions:
                raise ValueError(f"Session {session_id} đã tồn tại")
            
            # Lấy port
            port = custom_port or self._get_available_port()
            
            # Copy master profile (tự động xóa lịch sử)
            profile_dir = self._copy_master_profile(session_id)
            
            # Chuẩn bị Chrome arguments
            args = [
                self.chrome_path,
                f"--remote-debugging-port={port}",
                "--remote-allow-origins=*",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
            ]
            
            if headless:
                args.append("--headless=new")
            
            if os.name != "nt":
                args.append("--no-sandbox")
            
            if extra_args:
                args.extend(extra_args)
            
            # Khởi động Chrome
            print(f"[{session_id}] Khởi động Chrome trên port {port}...")
            process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            
            # Tạo session
            session = CDPSession(
                session_id=session_id,
                port=port,
                profile_dir=profile_dir,
                process=process,
                is_active=True
            )
            self.sessions[session_id] = session
            
            # Chờ CDP ready
            if not self._wait_for_cdp(port, timeout=30):
                self.stop_session(session_id)
                raise RuntimeError(f"Không thể kết nối CDP trên port {port}")
            
            print(f"[{session_id}] Session đã sẵn sàng tại http://localhost:{port}")
            return session
    
    def _wait_for_cdp(self, port: int, timeout: int = 30) -> bool:
        """Chờ CDP server sẵn sàng"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                response = requests.get(
                    f"http://localhost:{port}/json/version",
                    timeout=2
                )
                if response.status_code == 200:
                    return True
            except requests.exceptions.ConnectionError:
                time.sleep(0.5)
            except Exception:
                time.sleep(0.5)
        return False
    
    def get_cdp_url(self, session_id: str) -> str:
        """Lấy CDP WebSocket URL cho session"""
        session = self.get_session(session_id)
        try:
            response = requests.get(
                f"http://localhost:{session.port}/json",
                timeout=5
            )
            pages = response.json()
            if pages:
                return pages[0].get("webSocketDebuggerUrl", "")
        except Exception as e:
            raise RuntimeError(f"Không thể lấy CDP URL: {e}")
        return ""
    
    def get_session(self, session_id: str) -> CDPSession:
        """Lấy session theo ID"""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} không tồn tại")
        return self.sessions[session_id]
    
    def list_sessions(self) -> List[CDPSession]:
        """Liệt kê tất cả sessions đang active"""
        return list(self.sessions.values())
    
    def execute_cdp_command(
        self,
        session_id: str,
        method: str,
        params: Optional[Dict] = None
    ) -> Dict:
        """
        Thực thi lệnh CDP qua HTTP endpoint.
        
        Args:
            session_id: Session ID
            method: CDP method (e.g., "Page.navigate", "Runtime.evaluate")
            params: Parameters cho method
        """
        session = self.get_session(session_id)
        
        # Lấy session CDP ID
        try:
            response = requests.get(
                f"http://localhost:{session.port}/json",
                timeout=5
            )
            pages = response.json()
            if not pages:
                raise RuntimeError("Không có page nào đang mở")
            
            page_id = pages[0]["id"]
            
            # Send CDP command
            payload = {
                "id": 1,
                "method": method,
                "params": params or {}
            }
            
            response = requests.post(
                f"http://localhost:{session.port}/json/activate/{page_id}",
                timeout=5
            )
            
            # Sử dụng WebSocket cho CDP commands
            import websocket
            ws_url = pages[0].get("webSocketDebuggerUrl")
            
            if not ws_url:
                raise RuntimeError("Không thể lấy WebSocket URL")
            
            ws = websocket.create_connection(ws_url, timeout=10)
            ws.send(json.dumps(payload))
            result = ws.recv()
            ws.close()
            
            return json.loads(result)
            
        except Exception as e:
            raise RuntimeError(f"CDP command failed: {e}")
    
    def navigate(self, session_id: str, url: str) -> Dict:
        """Navigate đến URL trong session"""
        return self.execute_cdp_command(
            session_id,
            "Page.navigate",
            {"url": url}
        )
    
    def evaluate(self, session_id: str, expression: str) -> Dict:
        """Evaluate JavaScript trong session"""
        return self.execute_cdp_command(
            session_id,
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True
            }
        )
    
    def get_html(self, session_id: str) -> str:
        """Lấy HTML của page hiện tại - thử nhiều cách"""
        expressions = [
            "document.documentElement.innerHTML",
            "document.body.innerHTML",
            "document.documentElement.outerHTML",
        ]
        
        for expr in expressions:
            try:
                result = self.execute_cdp_command(
                    session_id,
                    "Runtime.evaluate",
                    {"expression": expr, "returnByValue": True}
                )
                value = result.get("result", {}).get("value", "")
                if value:
                    return value
            except Exception:
                continue
        
        return ""
    
    def stop_session(self, session_id: str, cleanup: bool = True):
        """
        Dừng một phiên và cleanup.
        
        Args:
            session_id: Session ID cần dừng
            cleanup: Xóa temp profile sau khi dừng
        """
        with self._lock:
            if session_id not in self.sessions:
                print(f"[{session_id}] Session không tồn tại")
                return
            
            session = self.sessions[session_id]
            
            # Kill Chrome process
            if session.process and session.process.poll() is None:
                print(f"[{session_id}] Đang dừng Chrome process...")
                session.process.terminate()
                try:
                    session.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    session.process.kill()
                    session.process.wait()
            
            # Cleanup temp profile
            if cleanup and os.path.exists(session.profile_dir):
                print(f"[{session_id}] Xóa temp profile...")
                try:
                    shutil.rmtree(session.profile_dir, ignore_errors=True)
                except Exception as e:
                    print(f"[{session_id}] Lỗi xóa profile: {e}")
            
            # Release port
            with self._port_lock:
                self._used_ports.discard(session.port)
            
            session.is_active = False
            del self.sessions[session_id]
            
            print(f"[{session_id}] Session đã dừng.")
    
    def stop_all_sessions(self):
        """Dừng tất cả sessions"""
        session_ids = list(self.sessions.keys())
        for sid in session_ids:
            self.stop_session(sid)
    
    def restart_session(
        self,
        session_id: str,
        headless: bool = False,
        extra_args: Optional[List[str]] = None
    ) -> CDPSession:
        """Restart một session (stop rồi start lại, xóa lịch sử)"""
        self.stop_session(session_id)
        return self.start_session(
            session_id=session_id,
            headless=headless,
            extra_args=extra_args
        )
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_all_sessions()


# ===== Convenience Functions =====

def create_controller(
    master_profile: str = "master",
    base_port: int = 9222
) -> MasterProfileController:
    """Tạo controller instance"""
    return MasterProfileController(
        master_profile_path=master_profile,
        base_port=base_port
    )


def run_parallel_sessions(
    tasks: List[Callable[[CDPSession], any]],
    controller: Optional[MasterProfileController] = None,
    max_workers: int = 4
) -> List:
    """
    Chạy nhiều tasks song song với đa phiên.
    
    Args:
        tasks: List các function nhận CDPSession làm tham số
        controller: Controller instance (tạo mới nếu None)
        max_workers: Số worker tối đa
    """
    should_cleanup = controller is None
    controller = controller or create_controller()
    
    results = []
    
    def run_task(task_func, index):
        session = controller.start_session(f"parallel_{index}")
        try:
            return task_func(session)
        finally:
            controller.stop_session(session.session_id)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(run_task, task, i)
            for i, task in enumerate(tasks)
        ]
        results = [f.result() for f in futures]
    
    if should_cleanup:
        controller.stop_all_sessions()
    
    return results


# ===== Example Usage =====

if __name__ == "__main__":
    # Ví dụ sử dụng single session
    print("=== Test Single Session ===")
    
    with MasterProfileController() as controller:
        # Session 1
        session1 = controller.start_session("test_1", headless=False)
        controller.navigate(session1.session_id, "https://facebook.com")
        time.sleep(3)
        html = controller.get_html(session1.session_id)
        print(f"Session 1 HTML length: {len(html)}")
        
        # Restart session (tự động xóa lịch sử)
        print("\nRestarting session (xóa lịch sử)...")
        session1 = controller.restart_session(session1.session_id, headless=False)
        controller.navigate(session1.session_id, "https://google.com")
        time.sleep(2)
        
        # Session 2 (song song)
        print("\n=== Test Multi Session ===")
        session2 = controller.start_session("test_2", headless=False)
        controller.navigate(session2.session_id, "https://github.com")
        time.sleep(2)
        
        print(f"\nActive sessions: {[s.session_id for s in controller.list_sessions()]}")
        
        # Cleanup tự động khi exit context
    
    print("\nAll sessions stopped.")
