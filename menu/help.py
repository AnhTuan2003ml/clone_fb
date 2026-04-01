"""
Help Menu Server - Device-specific templates
============================================
Flask server phục vụ trang help với template phù hợp cho từng loại thiết bị.
- Android: templates/Android/help.html
- iOS: templates/iOS/help.html
- Desktop: templates/Desktop/help.html
"""

import os
import sys
from flask import Flask, render_template, request

# Fix import path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
sys.path.insert(0, _parent_dir)

# Flask app - template folder trỏ đến thư mục templates của project
template_dir = os.path.join(_parent_dir, 'templates')
app = Flask(__name__, template_folder=template_dir)


def detect_device(user_agent: str) -> str:
    """Phát hiện thiết bị từ User-Agent"""
    ua = user_agent.lower()
    if "iphone" in ua or "ipad" in ua or "ios" in ua:
        return "iOS"
    if "android" in ua:
        return "Android"
    return "Desktop"


@app.route("/help")
def help_page():
    """Trang help - hiển thị template phù hợp với thiết bị"""
    user_agent = request.headers.get("User-Agent", "")
    device = detect_device(user_agent)
    
    print(f"[Help] User-Agent: {user_agent[:50]}...")
    print(f"[Help] Device: {device}")
    
    # Render template theo thiết bị
    template_map = {
        "iOS": "iOS/help.html",
        "Android": "Android/help.html",
        "Desktop": "Desktop/help.html"
    }
    template = template_map.get(device, "Desktop/help.html")
    
    return render_template(template)


def run_server(host="0.0.0.0", port=5001, open_browser=False):
    """Chạy Flask server"""
    url = f"http://localhost:{port}"
    print(f"\n[Help Server] Khởi động server tại {url}")
    print(f"[Help Server] Android -> templates/Android/help.html")
    print(f"[Help Server] iOS -> templates/iOS/help.html")
    print(f"[Help Server] Desktop -> templates/Desktop/help.html\n")
    
    if open_browser:
        import webbrowser
        webbrowser.open(url + "/help")
        print(f"[Help Server] Đã mở trình duyệt tại {url}/help")
    
    app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True
    )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Facebook Help Server")
    parser.add_argument("--port", "-p", type=int, default=5001, help="Port (mặc định: 5001)")
    parser.add_argument("--no-browser", action="store_true", help="Không tự động mở trình duyệt")
    
    args = parser.parse_args()
    
    run_server(port=args.port, open_browser=not args.no_browser)
