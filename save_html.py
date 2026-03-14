from playwright.sync_api import sync_playwright
import os

def fill_facebook_login(username: str, password: str, output_filename="templates/facebook_filled.html"):

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=False)

        context = browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9"
            }
        )

        page = context.new_page()

        try:

            print("Opening Facebook...")

            page.goto(
                "https://www.facebook.com/?locale=en_US",
                wait_until="domcontentloaded"
            )

            page.wait_for_selector('input[name="email"]')

            print("Filling email...")
            page.fill('input[name="email"]', username)

            print("Filling password...")
            page.fill('input[name="pass"]', password)

            # chờ 2s để DOM update
            page.wait_for_timeout(2000)

            html = page.content()

            os.makedirs("templates", exist_ok=True)

            filepath = os.path.join("templates", output_filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)

            print("Saved:", filepath)

            input("Press Enter to close browser...")

        except Exception as e:
            print("Error:", e)

        finally:
            browser.close()


if __name__ == "__main__":

    USERNAME = "0905000000"
    PASSWORD = "aaaaa"

    fill_facebook_login(USERNAME, PASSWORD)