from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import os
import shutil
import tempfile
import time
import sys


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
) -> str:
    """
    Đăng nhập Facebook và trả về HTML sau khi login.

    - Tạo bản sao tạm thời của profile master, xóa sạch cookies/session/IndexedDB.
    - Nếu copy thất bại, thử dùng trực tiếp master (kèm cảnh báo).
    - Chờ tối đa `timeout` ms cho đến khi URL rời trang login.
    - Nếu URL chuyển sang trang 2FA loại two_factor thì vẫn trả về HTML (để client hiển thị).
    - Nếu URL đang ở trang authentication thì tiếp tục đợi cho đến khi rời trang đó rồi mới lấy HTML.
    - Trả về chuỗi rỗng nếu có lỗi không lấy được HTML.
    """
    html_content = ""
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

        # --- Xóa sạch session/cookies khỏi profile tạm ---
        print("Đang xóa cookies, session, IndexedDB khỏi profile tạm...")
        clean_profile(temp_profile_dir)
        print("Đã xóa xong.")

        # --- Khởi động Playwright ---
        playwright = sync_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
        ]
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

        # --- Chờ URL thay đổi (kể cả chuyển sang two_step_verification, checkpoint, ...) ---
        initial_url = page.url
        print(f"URL trước khi đăng nhập: {initial_url}")

        try:
            # Chờ URL thay đổi (rời khỏi trang login)
            page.wait_for_function(
                "url => window.location.href !== url",
                arg=initial_url,
                timeout=timeout
            )
            print(f"URL đã thay đổi sau khi đăng nhập: {page.url}")

            current_url = page.url

            # Nếu đang ở trang yêu cầu xác thực 2 bước dạng authentication
            # -> tiếp tục chờ đến khi rời trang này (KHÔNG trả HTML của trang authentication)
            if "two_step_verification/authentication" in current_url:
                print("Đang ở trang two_step_verification/authentication, tiếp tục chờ user xác thực...")
                try:
                    page.wait_for_function(
                        "() => !window.location.href.includes('two_step_verification/authentication')",
                        timeout=timeout
                    )
                    print(f"Rời trang two_step_verification/authentication, URL hiện tại: {page.url}")
                except PlaywrightTimeoutError:
                    print(
                        f"Hết thời gian chờ rời trang two_step_verification/authentication ({timeout}ms). "
                        f"URL hiện tại: {page.url}."
                    )

            # Sau khi đã rời trang login (và nếu có, rời luôn trang two_step_verification/authentication),
            # chờ trang tải ổn định hơn một chút
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                print("Hết thời gian chờ networkidle, dùng DOM hiện tại.")

            # Đợi thêm một chút cho JS client-side render xong
            time.sleep(3)

        except PlaywrightTimeoutError:
            print(
                f"Hết thời gian chờ ({timeout}ms). "
                f"URL hiện tại: {page.url}. "
                "Có thể đang chờ captcha/2FA hoặc đăng nhập thất bại."
            )

        # --- Lấy HTML hiện tại (có thể là feed, two_factor, checkpoint, ...) ---
        html_content = page.content()

        # Chuyển các đường dẫn tương đối (/path) thành tuyệt đối https://www.facebook.com/path
        # để khi render ở domain của bạn vẫn load đúng hình ảnh / CSS từ Facebook.
        if html_content:
            try:
                base_fb = "https://www.facebook.com"
                html_content = html_content.replace('src="/', f'src="{base_fb}/')
                html_content = html_content.replace('href="/', f'href="{base_fb}/')
            except Exception as _rewrite_err:
                print(f"Lỗi khi rewrite URL tương đối -> tuyệt đối: {_rewrite_err}")

        print(f"Đã lấy HTML ({len(html_content)} ký tự).")

    except Exception as e:
        print(f"Lỗi không xác định: {e}")

    finally:
        # if context:
        #     try:
        #         context.close()
        #     except Exception:
        #         pass
        # if playwright:
        #     try:
        #         playwright.stop()
        #     except Exception:
        #         pass
        # # Dọn dẹp thư mục tạm (không xóa nếu đang dùng master trực tiếp)
        # if temp_profile_dir and not used_master_directly and os.path.exists(temp_profile_dir):
        #     try:
        #         shutil.rmtree(temp_profile_dir)
        #         print(f"Đã xóa thư mục tạm: {temp_profile_dir}")
        #     except Exception as e:
        #         print(f"Không thể xóa thư mục tạm {temp_profile_dir}: {e}")
        pass

    return html_content