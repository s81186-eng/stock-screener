import os
import re
import time
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

        # Step 1: user id + password
        page.fill("#userid", KITE_USER_ID)
        page.fill("#password", KITE_PASSWORD)
        page.click("button[type='submit']")

        # Step 2: TOTP
        page.wait_for_selector("input[type='number'], input[type='text']", timeout=15000)
        totp_code = pyotp.TOTP(KITE_TOTP_SECRET).now()
        totp_inputs = page.query_selector_all("input[type='number'], input[type='text']")
        # Use the last visible numeric/text input on the page as the TOTP field
        totp_inputs[-1].fill(totp_code)

        # Wait for redirect to our site with request_token in the URL
        page.wait_for_url(re.compile(r"request_token="), timeout=20000)
        final_url = page.url
        browser.close()

    request_token = final_url.split("request_token=")[1].split("&")[0]

    kite = KiteConnect(api_key=KITE_API_KEY)
    session_data = kite.generate_session(request_token, api_secret=KITE_API_SECRET)
    return session_data["access_token"]


if __name__ == "__main__":
    token = get_access_token()
    print("ACCESS_TOKEN=" + token)
