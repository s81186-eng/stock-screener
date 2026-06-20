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


def get_visible_inputs(page):
    inputs = page.query_selector_all("input")
    visible = []
    for inp in inputs:
        try:
            if inp.is_visible():
                visible.append(inp)
        except Exception:
            pass
    return visible


def get_access_token():
    kite = KiteConnect(api_key=KITE_API_KEY)
    login_url = kite.login_url()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(login_url, wait_until="networkidle")
        page.wait_for_timeout(1500)

        # Step 1: find visible inputs, fill userid (non-password) and password
        visible_inputs = get_visible_inputs(page)
        print(f"Step 1: found {len(visible_inputs)} visible inputs")
        for i, inp in enumerate(visible_inputs):
            print(f"  [{i}] type={inp.get_attribute('type')}")

        userid_input = None
        password_input = None
        for inp in visible_inputs:
            input_type = (inp.get_attribute("type") or "text").lower()
            if input_type == "password" and password_input is None:
                password_input = inp
            elif input_type != "checkbox" and userid_input is None:
                userid_input = inp

        if userid_input is None or password_input is None:
            page.screenshot(path="debug_2_fields_not_found.png")
            raise Exception("Could not identify userid/password fields")

        userid_input.click()
        userid_input.fill(KITE_USER_ID)
        password_input.click()
        password_input.fill(KITE_PASSWORD)

        print("userid field value now:", userid_input.input_value())
        print("password field value now:", "*" * len(password_input.input_value()))

        page.screenshot(path="debug_2_filled.png")

        page.click("button:has-text('Login')")
        page.wait_for_timeout(3000)
        page.screenshot(path="debug_3_after_submit.png")
        print("URL after step 1 submit:", page.url)

        # Step 2: TOTP page
        page.wait_for_timeout(1500)
        visible_inputs_2 = get_visible_inputs(page)
        print(f"Step 2: found {len(visible_inputs_2)} visible inputs")

        totp_field = None
        for inp in visible_inputs_2:
            input_type = (inp.get_attribute("type") or "text").lower()
            if input_type != "checkbox":
                totp_field = inp

        if totp_field is None:
            page.screenshot(path="debug_4_no_totp_field.png")
            with open("debug_page_content.html", "w") as f:
                f.write(page.content())
            raise Exception("Could not find a TOTP input field")

        totp_code = pyotp.TOTP(KITE_TOTP_SECRET).now()
        print("Generated TOTP:", totp_code)
        totp_field.click()
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
