import os
import re
import pyotp
from playwright.sync_api import sync_playwright
from kiteconnect import KiteConnect

KITE_API_KEY = os.environ["KITE_API_KEY"]
KITE_API_SECRET = os.environ["KITE_API_SECRET"]
KITE_USER_ID = os.environ["KITE_USER_ID"]
KITE_PASSWORD = os.environ["KITE_PASSWORD"]
KITE_TOTP_SECRET = os.environ["KITE_TOTP_SECRET"]


def get_access_token():
    kite = KiteConnect(api_key=KITE_API_KEY)
    login_url = kite.login_url()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(login_url, wait_until="networkidle")
        page.wait_for_timeout(1500)

        # Step 1: type userid character-by-character (simulates real keystrokes)
        userid_locator = page.locator('input:not([type="password"]):not([type="checkbox"])').first
        password_locator = page.locator('input[type="password"]').first

        userid_locator.click()
        userid_locator.press_sequentially(KITE_USER_ID, delay=80)
        page.wait_for_timeout(300)
        print("userid field value now:", userid_locator.input_value())

        password_locator.click()
        password_locator.press_sequentially(KITE_PASSWORD, delay=80)
        page.wait_for_timeout(300)
        print("password field length now:", len(password_locator.input_value()))

        page.screenshot(path="debug_2_filled.png")

        page.click("button:has-text('Login')")
        page.wait_for_timeout(3000)
        page.screenshot(path="debug_3_after_submit.png")
        print("URL after step 1 submit:", page.url)

        # Step 2: TOTP page
        page.wait_for_timeout(1500)
        totp_locator = page.locator('input:not([type="checkbox"])').first
        totp_code = pyotp.TOTP(KITE_TOTP_SECRET).now()
        print("Generated TOTP:", totp_code)

        totp_locator.click()
        totp_locator.press_sequentially(totp_code, delay=80)
        page.wait_for_timeout(300)
        print("totp field value now:", totp_locator.input_value())

        page.screenshot(path="debug_5_totp_filled.png")
        page.wait_for_timeout(2000)

        print("URL before final wait:", page.url)

        try:
            page.wait_for_url(re.compile(r"request_token="), timeout=15000)
        except Exception as e:
            page.screenshot(path="debug_6_timeout.png")
            with open("debug_page_content.html", "w") as f:
                f.write(page.content())
            print("FAILED waiting for request_token. Final URL was:", page.url)
            browser.close()
            raise e

        final_url = page.url
        browser.close()

    request_token = final_url.split("request_token=")[1].split("&")[0]

    kite = KiteConnect(api_key=KITE_API_KEY)
    session_data = kite.generate_session(request_token, api_secret=KITE_API_SECRET)
    return session_data["access_token"]


if __name__ == "__main__":
    token = get_access_token()
    print("ACCESS_TOKEN=" + token)
