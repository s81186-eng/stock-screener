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


def set_value_js(page, selector, value):
    page.eval_on_selector(
        selector,
        """(el, value) => {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, value);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        value,
    )


def get_access_token():
    kite = KiteConnect(api_key=KITE_API_KEY)
    login_url = kite.login_url()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(login_url, wait_until="networkidle")
        page.wait_for_selector("#userid", timeout=15000)
        page.wait_for_timeout(1000)

        # Step 1: set userid + password directly via JS (bypasses flaky Vue input handling)
        set_value_js(page, "#userid", KITE_USER_ID)
        set_value_js(page, "#password", KITE_PASSWORD)
        page.wait_for_timeout(300)

        print("userid field value now:", page.eval_on_selector("#userid", "el => el.value"))
        print("password field length now:", len(page.eval_on_selector("#password", "el => el.value")))

        page.screenshot(path="debug_2_filled.png")

        page.click("button:has-text('Login')")
        page.wait_for_timeout(3000)
        page.screenshot(path="debug_3_after_submit.png")
        print("URL after step 1 submit:", page.url)

        # Step 2: TOTP page — find the visible non-checkbox input and fill it the same way
        page.wait_for_timeout(1500)
        visible_inputs = [inp for inp in page.query_selector_all("input") if inp.is_visible()]
        totp_input = None
        for inp in visible_inputs:
            if (inp.get_attribute("type") or "text").lower() != "checkbox":
                totp_input = inp

        if totp_input is None:
            page.screenshot(path="debug_4_no_totp_field.png")
            with open("debug_page_content.html", "w") as f:
                f.write(page.content())
            raise Exception("Could not find a TOTP input field")

        totp_code = pyotp.TOTP(KITE_TOTP_SECRET).now()
        print("Generated TOTP:", totp_code)

        totp_id = totp_input.get_attribute("id")
        if totp_id:
            set_value_js(page, f"#{totp_id}", totp_code)
        else:
            totp_input.evaluate(
                """(el, value) => {
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(el, value);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                totp_code,
            )

        page.wait_for_timeout(300)
        print("totp field value now:", totp_input.input_value())
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
