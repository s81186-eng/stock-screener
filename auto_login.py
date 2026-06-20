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
        page.wait_for_timeout(1000)

        # Step 1: user id is the first text input, password is the password-type input
        userid_field = page.locator('input[type="text"]').first
        password_field = page.locator('input[type="password"]').first

        userid_field.wait_for(state="visible", timeout=15000)
        userid_field.fill(KITE_USER_ID)
        password_field.fill(KITE_PASSWORD)
        page.screenshot(path="debug_2_filled.png")

        page.click("button:has-text('Login')")
        page.wait_for_timeout(3000)
        page.screenshot(path="debug_3_after_submit.png")
        print("URL after step 1 submit:", page.url)

        # Step 2: TOTP page
        page.wait_for_timeout(1500)
        all_inputs = page.query_selector_all("input")
        print(f"Found {len(all_inputs)} input fields on this page")

        totp_field = None
        for inp in all_inputs:
            input_type = (inp.get_attribute("type") or "").lower()
            if input_type in ("text", "number", "tel", "password") and inp.is_visible():
                placeholder = (inp.get_attribute("placeholder") or "")
                print(f"  candidate input: type={input_type} placeholder={placeholder}")
                totp_field = inp

        if totp_field is None:
            page.screenshot(path="debug_4_no_totp_field.png")
            with open("debug_page_content.html", "w") as f:
                f.write(page.content())
            raise Exception("Could not find a TOTP input field. See debug_4 screenshot.")

        totp_code = pyotp.TOTP(KITE_TOTP_SECRET).now()
        print("Generated TOTP:", totp_code)
        totp_field.fill(totp_code)
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
