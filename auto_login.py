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
        page.screenshot(path="debug_1_initial.png")
        print("URL after goto:", page.url)

        # Step 1: user id + password
        page.fill("#userid", KITE_USER_ID)
        page.fill("#password", KITE_PASSWORD)
        page.screenshot(path="debug_2_filled.png")
        page.click("button[type='submit']")
        page.wait_for_timeout(3000)
        page.screenshot(path="debug_3_after_submit.png")
        print("URL after step 1 submit:", page.url)

        # Step 2: TOTP
        totp_code = pyotp.TOTP(KITE_TOTP_SECRET).now()
        print("Generated TOTP:", totp_code)

        all_inputs = page.query_selector_all("input")
        print(f"Found {len(all_inputs)} input fields on TOTP page")
        for i, inp in enumerate(all_inputs):
            try:
                print(f"  input[{i}]: type={inp.get_attribute('type')} id={inp.get_attribute('id')} name={inp.get_attribute('name')} placeholder={inp.get_attribute('placeholder')}")
            except Exception:
                pass

        if all_inputs:
            all_inputs[-1].fill(totp_code)
            page.screenshot(path="debug_4_totp_filled.png")
            page.wait_for_timeout(2000)

        print("URL before final wait:", page.url)
        page.screenshot(path="debug_5_before_wait.png")

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
