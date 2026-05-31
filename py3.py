import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import string
import json
import os
import re
import asyncio
import traceback
import sys
import discord
from discord.ext import commands
import threading
import gc
import http.server
import socketserver
import ssl
import urllib.request

# --- CONFIG ---
URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=9199bf20-a13f-4107-85dc-02114787ef48&scope=https%3A%2F%2Foutlook.office.com%2F.default%20openid%20profile%20offline_access&redirect_uri=https%3A%2F%2Foutlook.live.com%2Fmail%2F&client-request-id=85af84fb-4838-c204-f618-76e540231109&response_mode=fragment&client_info=1&prompt=select_account&nonce=019e35f5-4ebc-7f28-8e36-611bb37f46ef&state=eyJpZCI6IjAxOWUzNWY1LTRlYmItNzdmZS04MzkwLTVlMmMzZTFhN2FiMiIsIm1ldGEiOnsiaW50ZXJhY3Rpb25UeXBlIjoicmVkaXJlY3QifX0%3D%7CaHR0cHM6Ly9vdXRsb29rLmxpdmUuY29tL21haWwvP2N1bHR1cmU9ZW4tdXMmY291bnRyeT11cw&claims=%7B%22access_token%22%3A%7B%22xms_cc%22%3A%7B%22values%22%3A%5B%22CP1%22%5D%7D%7D%7D&x-client-SKU=msal.js.browser&x-client-VER=4.28.2&response_type=code&code_challenge=Y-gIvtWec47bQ-tJO49QiNIoRYFseu5HdBprFFN3Af0&code_challenge_method=S256&cobrandid=ab0455a0-8d03-46b9-b18b-df2f57b9e44c&fl=dob,flname,wld&sso_reload=true"

CHATGPT_SESSION_URL = "https://chatgpt.com/api/auth/session"
SESSION_FILE_PATH = "chatgpt_session.txt"

# Max concurrent Chrome instances to protect server resources
bot_semaphore = asyncio.Semaphore(3)

# Load .env file manually
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if "=" in line:
                parts = line.strip().split("=", 1)
                if len(parts) == 2:
                    os.environ[parts[0].strip()] = parts[1].strip()

def setup_proxy_extension(proxy_string):
    cleaned = proxy_string.replace("http://", "").replace("https://", "")
    auth_part, ip_port = cleaned.split("@", 1)
    username, password = auth_part.split(":", 1)
    ip, port = ip_port.split(":", 1)
    
    plugin_dir = os.path.join(os.getcwd(), "proxy_auth_plugin")
    if not os.path.exists(plugin_dir):
        os.makedirs(plugin_dir)
        
    manifest_json = """{
    "version": "1.0.0",
    "manifest_version": 2,
    "name": "Chrome Proxy",
    "permissions": [
        "proxy",
        "tabs",
        "unlimitedStorage",
        "storage",
        "<all_urls>",
        "webRequest",
        "webRequestBlocking"
    ],
    "background": {
        "scripts": ["background.js"]
    },
    "minimum_chrome_version":"22.0.0"
}"""
    
    background_js = f"""var config = {{
    mode: "fixed_servers",
    rules: {{
      singleProxy: {{
        scheme: "http",
        host: "{ip}",
        port: parseInt({port})
      }}
    }}
  }};

chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

chrome.webRequest.onAuthRequired.addListener(
    function callbackFn(details) {{
        return {{
            authCredentials: {{
                username: "{username}",
                password: "{password}"
            }}
        }};
    }},
    {{urls: ["<all_urls>"]}},
    ['blocking']
);"""

    with open(os.path.join(plugin_dir, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(manifest_json)
    with open(os.path.join(plugin_dir, "background.js"), "w", encoding="utf-8") as f:
        f.write(background_js)
        
    return plugin_dir

def get_chrome_options():
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    
    PROXIES = [
        "http://ffbutrps:h9l80ao50ael@38.154.203.95:5863",
        "http://ffbutrps:h9l80ao50ael@198.105.121.200:6462",
        "http://ffbutrps:h9l80ao50ael@64.137.96.74:6641",
        "http://ffbutrps:h9l80ao50ael@209.127.138.10:5784",
        "http://ffbutrps:h9l80ao50ael@38.154.185.97:6370",
        "http://ffbutrps:h9l80ao50ael@84.247.60.125:6095",
        "http://ffbutrps:h9l80ao50ael@142.111.67.146:5611",
        "http://ffbutrps:h9l80ao50ael@191.96.254.138:6185",
        "http://ffbutrps:h9l80ao50ael@31.58.9.4:6077",
        "http://ffbutrps:h9l80ao50ael@64.137.10.153:5803"
    ]
    proxy = random.choice(PROXIES)
    print(f"Using proxy: {proxy.split('@')[-1]}")
    plugin_path = setup_proxy_extension(proxy)
    options.add_argument(f'--load-extension={plugin_path}')
    
    # Configure required container sandbox arguments in cloud/Docker environments
    is_container = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
    if is_container:
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        
    return options

def create_driver(options=None):
    try:
        print("Initializing Chrome driver (auto-detect)...")
        fresh_options = get_chrome_options()
        return uc.Chrome(options=fresh_options, headless=False, use_subprocess=True)
    except Exception as e:
        err_msg = str(e)
        print(f"Auto-detect failed: {err_msg}")
        
        detected_ver = None
        match1 = re.search(r"Current browser version is (\d+)", err_msg)
        match2 = re.search(r"only supports Chrome version (\d+)", err_msg)
        match3 = re.search(r"supports Chrome version (\d+)", err_msg)
        
        if match1:
            detected_ver = int(match1.group(1))
        elif match2:
            detected_ver = int(match2.group(1))
        elif match3:
            detected_ver = int(match3.group(1))
            
        if not detected_ver:
            try:
                import subprocess
                out = subprocess.check_output(["google-chrome", "--version"]).decode("utf-8")
                detected_ver = int(out.strip().split()[-1].split(".")[0])
                print(f"Detected Chrome version via CLI: {detected_ver}")
            except:
                try:
                    out = subprocess.check_output(["chromium-browser", "--version"]).decode("utf-8")
                    detected_ver = int(out.strip().split()[-1].split(".")[0])
                    print(f"Detected Chromium version via CLI: {detected_ver}")
                except:
                    pass

        if detected_ver:
            print(f"Self-Healing: Detected Chrome version {detected_ver}. Initializing driver...")
            try:
                retry_options = get_chrome_options()
                return uc.Chrome(options=retry_options, version_main=detected_ver, headless=False, use_subprocess=True)
            except Exception as retry_err:
                print(f"Self-Healing retry failed for version {detected_ver}: {retry_err}")

        if os.name == 'nt':
            major_version = None
            try:
                import winreg
                reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                version, _ = winreg.QueryValueEx(reg_key, "version")
                winreg.CloseKey(reg_key)
                major_version = int(version.split(".")[0])
                print(f"Detected Chrome major version: {major_version} (HKCU)")
            except Exception:
                try:
                    import winreg
                    reg_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                    version, _ = winreg.QueryValueEx(reg_key, "version")
                    winreg.CloseKey(reg_key)
                    major_version = int(version.split(".")[0])
                    print(f"Detected Chrome major version: {major_version} (HKLM)")
                except Exception:
                    pass

            if major_version:
                try:
                    print(f"Initializing Chrome driver with version_main={major_version}...")
                    reg_options = get_chrome_options()
                    return uc.Chrome(options=reg_options, version_main=major_version, headless=False, use_subprocess=True)
                except Exception as reg_err:
                    print(f"Failed with version_main={major_version}: {reg_err}")

        for ver in [148, 147, 149, 146]:
            try:
                print(f"Initializing Chrome driver with fallback version_main={ver}...")
                fallback_options = get_chrome_options()
                return uc.Chrome(options=fallback_options, version_main=ver, headless=False, use_subprocess=True)
            except Exception:
                pass

        print("All Chrome driver initialization attempts failed. Trying final fallback...")
        final_options = get_chrome_options()
        return uc.Chrome(options=final_options, headless=False, use_subprocess=True)

def clear_session_file():
    try:
        if os.path.exists(SESSION_FILE_PATH):
            os.remove(SESSION_FILE_PATH)
            print("Cleared previous session file")
    except Exception:
        pass

def run_flow(email, password):
    max_retries = 2
    retry_count = 0
    
    while retry_count < max_retries:
        clear_session_file()
        
        driver = create_driver()
        wait = WebDriverWait(driver, 30)

        try:
            driver.get(URL)
            print("Navigated to Outlook URL successfully.")
            
            original_window = driver.current_window_handle
            
            driver.switch_to.new_window('tab')
            chatgpt_window = driver.current_window_handle
            driver.get('https://chatgpt.com/')
            print("Opened ChatGPT in a second tab.")
            
            time.sleep(1)
            current_url = driver.current_url.lower()
            print(f"Current ChatGPT URL: {current_url}")
            
            if "/auth/login" in current_url or "auth/login" in current_url:
                print("Detected /auth/login page - restarting flow...")
                retry_count += 1
                driver.quit()
                driver = None
                print(f"Restart attempt {retry_count}/{max_retries}...")
                time.sleep(2)
                continue
            
            print("Waiting for ChatGPT login button...")
            chatgpt_login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='login-button']")))
            chatgpt_login_btn.click()
            print("Clicked ChatGPT Log in button.")
            
            print("Waiting for ChatGPT email input...")
            chatgpt_email_input = wait.until(EC.element_to_be_clickable((By.ID, "email")))
            chatgpt_email_input.clear()
            chatgpt_email_input.send_keys(email)
                
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", chatgpt_email_input)
            print("Entered email into ChatGPT successfully.")
            
            print("Waiting for ChatGPT Continue button...")
            chatgpt_continue_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']")))
            chatgpt_continue_btn.click()
            print("Clicked ChatGPT Continue button.")
            
            driver.switch_to.window(original_window)
            
            print(f"Typing email: {email}")
            email_input = wait.until(EC.element_to_be_clickable((By.ID, "i0116")))
            email_input.clear()
            email_input.send_keys(email)
                
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_input)
            print("Email entered successfully.")
            
            time.sleep(1)
            next_btn = wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9")))
            next_btn.click()
            print("Clicked 'Next' button.")

            print("Waiting for password field...")
            password_input = wait.until(EC.element_to_be_clickable((By.ID, "passwordEntry")))
            password_input.clear()
            password_input.send_keys(password)
                
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", password_input)
            print("Password entered successfully.")
            
            time.sleep(1)
            submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='primaryButton']")))
            submit_btn.click()
            print("Clicked 'Next' (Submit) button.")
            
            print("Checking for 'Skip for now' / security setup prompts...")
            time.sleep(2)
            for i in range(7):
                try:
                    cancel_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Cancel')] | //input[@id='idCancel'] | //*[@id='idCancel'] | //input[@value='Cancel'] | //*[contains(text(), 'Cancel')]")
                    passkey_header = driver.find_elements(By.XPATH, "//*[contains(text(), 'Setting up your passkey') or contains(text(), 'passkey')]")
                    
                    if cancel_btns and (cancel_btns[0].is_displayed() or (passkey_header and len(passkey_header) > 0)):
                        cancel_btns[0].click()
                        print(f"Clicked Microsoft Passkey setup 'Cancel' button (Attempt {i+1})!")
                        time.sleep(4)
                        continue
                    
                    skip_btns = driver.find_elements(By.ID, "iShowSkip")
                    if skip_btns and skip_btns[0].is_displayed():
                        skip_btns[0].click()
                        print(f"Clicked 'Skip for now' (Attempt {i+1}).")
                        time.sleep(3)
                    else:
                        skip_btns_xpath = driver.find_elements(By.XPATH, "//*[contains(@id, 'iShowSkip') or contains(text(), 'Skip for now')]")
                        if skip_btns_xpath and skip_btns_xpath[0].is_displayed():
                            skip_btns_xpath[0].click()
                            print(f"Clicked 'Skip for now' via XPath (Attempt {i+1}).")
                            time.sleep(3)
                        else:
                            break
                except Exception as e_skip:
                    print(f"Skip/Cancel loop iteration {i+1} handled exception: {e_skip}")
                    break
            
            print("Waiting for 'Stay signed in' prompt...")
            try:
                no_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='secondaryButton']")))
                no_btn.click()
                print("Clicked 'No' button on 'Stay signed in' prompt.")
            except Exception:
                try:
                    no_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'No') or contains(text(), 'no')]")))
                    no_btn.click()
                    print("Clicked 'No' button on 'Stay signed in' prompt via text match.")
                except Exception as stay_signed_err:
                    print("Stay signed in prompt did not appear or failed:", stay_signed_err)
            
            print("Inbox loaded. Searching for ChatGPT verification emails...")
            time.sleep(1)
            chatgpt_email_found = False
            extracted_code = None
            
            try:
                search_input = wait.until(EC.element_to_be_clickable((By.ID, "topSearchInput")))
                search_input.click()
                time.sleep(1)
                search_input.clear()
                
                search_term = "chatgpt code"
                print(f"Typing search query: {search_term}")
                search_input.send_keys(search_term)
                    
                time.sleep(0.5)
                search_input.send_keys("\n")
                print("Search submitted successfully.")
                
                print("Waiting for search results to display...")
                time.sleep(2)
                
                empty_state = driver.find_elements(By.XPATH, "//span[contains(text(), 'No more results to show')]")
                if empty_state:
                    print("No search results found! Opening TOPMOST email...")
                    time.sleep(0.5)
                    top_email = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")))
                    top_email.click()
                    print("Clicked TOPMOST email!")
                    chatgpt_email_found = True
                else:
                    items = driver.find_elements(By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")
                    print(f"Found {len(items)} email list items to scan.")
                    
                    for item in items:
                        text = (item.text or "")
                        aria_label = (item.get_attribute("aria-label") or "")
                        combined_text = (text + " " + aria_label).lower()
                        
                        if "chatgpt" in combined_text and "verification code" in combined_text or "temporary chatgpt login code" in combined_text:
                            code_match = re.search(r'verification code\D*(\d{6})', combined_text, re.IGNORECASE)
                            if code_match:
                                extracted_code = code_match.group(1)
                                print(f"Extracted verification code from preview: {extracted_code}")
                            
                            item.click()
                            print("Clicked ChatGPT verification email!")
                            chatgpt_email_found = True
                            break
            except Exception as scan_err:
                print("Error during search and scan:", scan_err)
                
            if not chatgpt_email_found:
                print("OpenAI verification email not found. Attempting Resend Email procedure...")
                try:
                    driver.switch_to.window(chatgpt_window)
                    print("Switched to ChatGPT window to trigger resend...")
                    
                    time.sleep(0.5)
                    resend_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[name='intent'][value='resend']")))
                    resend_btn.click()
                    print("Clicked 'Resend email' button in ChatGPT!")
                    
                    driver.switch_to.window(original_window)
                    print("Switched back to Outlook window...")
                    time.sleep(4)
                    
                    search_input = wait.until(EC.element_to_be_clickable((By.ID, "topSearchInput")))
                    search_input.click()
                    search_input.clear()
                    search_input.send_keys("chatgpt code")
                    search_input.send_keys("\n")
                    print("Search refreshed.")
                    time.sleep(3)
                    
                    empty_state = driver.find_elements(By.XPATH, "//span[contains(text(), 'No more results to show')]")
                    if empty_state:
                        print("No search results! Opening TOPMOST email...")
                        time.sleep(2)
                        top_email = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")))
                        top_email.click()
                        print("Clicked TOPMOST email!")
                        chatgpt_email_found = True
                    else:
                        items = driver.find_elements(By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")
                        for item in items:
                            text = (item.text or "")
                            aria_label = (item.get_attribute("aria-label") or "")
                            combined_text = (text + " " + aria_label).lower()
                            
                            if "chatgpt" in combined_text and "verification code" in combined_text or "temporary chatgpt login code" in combined_text:
                                code_match = re.search(r'verification code\D*(\d{6})', combined_text, re.IGNORECASE)
                                if code_match:
                                    extracted_code = code_match.group(1)
                                    print(f"Extracted verification code: {extracted_code}")
                                item.click()
                                print("Clicked ChatGPT verification email!")
                                chatgpt_email_found = True
                                break
                except Exception as resend_err:
                    print("Failed to auto-resend:", resend_err)
                    
            if not chatgpt_email_found:
                print("OpenAI verification email not found in scan loop.")
                # Keeping browser open as requested
                return False, None
                
            time.sleep(5)

            print("Monitoring for OpenAI verification codes...")
            
            start_time = time.time()
            last_resend_time = time.time()
            while time.time() - start_time < 300:
                try:
                    if time.time() - last_resend_time > 30:
                        print("OTP code has not arrived in 30 seconds. Switching to ChatGPT to resend...")
                        try:
                            driver.switch_to.window(chatgpt_window)
                            time.sleep(0.5)
                            
                            resend_btn = None
                            for selector in [
                                "button[name='intent'][value='resend']",
                                "button[value='resend']",
                                "//button[contains(text(), 'Resend email') or contains(., 'Resend')]"
                            ]:
                                try:
                                    if selector.startswith("//"):
                                        resend_btn = driver.find_element(By.XPATH, selector)
                                    else:
                                        resend_btn = driver.find_element(By.CSS_SELECTOR, selector)
                                    if resend_btn and resend_btn.is_displayed():
                                        break
                                except:
                                    continue
                            
                            if resend_btn:
                                resend_btn.click()
                                print("Clicked 'Resend email' button in ChatGPT!")
                                time.sleep(2)
                            else:
                                print("Resend email button not found on ChatGPT tab.")
                                
                            driver.switch_to.window(original_window)
                            print("Switched back to Outlook window. Refreshing search...")
                            
                            search_input = wait.until(EC.element_to_be_clickable((By.ID, "topSearchInput")))
                            search_input.click()
                            search_input.clear()
                            search_input.send_keys("chatgpt code")
                            search_input.send_keys("\n")
                            time.sleep(3)
                        except Exception as resend_err:
                            print("Failed to auto-resend during monitoring loop:", resend_err)
                            try:
                                driver.switch_to.window(original_window)
                            except:
                                pass
                        
                        last_resend_time = time.time()

                    code_to_enter = None
                    
                    try:
                        elements = driver.find_elements(By.XPATH, "//*[contains(@style, 'Menlo') or contains(@style, 'Monaco') or contains(@style, 'F3F3F3')]")
                        for elem in elements:
                            text = elem.text.strip()
                            if len(text) == 6 and text.isdigit():
                                code_to_enter = text
                                print(f"Copied code from styled element: {code_to_enter}")
                                break
                    except Exception:
                        pass
                    
                    if not code_to_enter and extracted_code:
                        code_to_enter = extracted_code
                        print(f"Using pre-extracted code: {code_to_enter}")
                    
                    if not code_to_enter:
                        try:
                            page_text = driver.find_element(By.TAG_NAME, "body").text
                            match = re.search(r'(?:continue|code):\s*(\d{6})', page_text, re.IGNORECASE)
                            if match:
                                code_to_enter = match.group(1)
                            else:
                                matches = re.findall(r'\b\d{6}\b', page_text)
                                if matches:
                                    code_to_enter = matches[0]
                        except Exception:
                            pass
                                
                    if code_to_enter:
                        print(f"FOUND VERIFICATION CODE: {code_to_enter}")
                        
                        driver.switch_to.window(chatgpt_window)
                        print("Entering code in ChatGPT...")
                        
                        code_input = wait.until(EC.element_to_be_clickable((By.NAME, "code")))
                        code_input.clear()
                        code_input.send_keys(code_to_enter)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", code_input)
                        
                        try:
                            time.sleep(0.5)
                            verify_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[name='intent'][value='validate']")))
                            verify_btn.click()
                            print("Clicked Continue to verify.")
                            
                            # Wait for redirect to finish and dashboard to load
                            print("Waiting for login to complete and redirect back to ChatGPT...")
                            WebDriverWait(driver, 35).until(
                                lambda d: "chatgpt.com" in d.current_url.lower() and "auth" not in d.current_url.lower()
                            )
                            print("Redirect successful. User is fully logged in!")
                            time.sleep(3) # Let session and cookies settle
                        except Exception as e_verify:
                            print(f"Warning during post-verification redirection: {e_verify}")
                            time.sleep(8)
                        
                        return True, driver
                except Exception as e:
                    print("Error during code checking cycle:", e)
                
                time.sleep(2)
            
            print("Search timed out.")
            # Keeping browser open as requested
            return False, None
            
        except Exception as e:
            print("Flow failed:")
            traceback.print_exc()
            # Keeping browser open as requested
            return False, None

def save_session_to_file(pre_text):
    try:
        with open(SESSION_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(pre_text)
        print(f"Saved to: {os.path.abspath(SESSION_FILE_PATH)}")
    except Exception as e:
        print(f"Failed to save: {e}")

def fill_profile_form(driver):
    print("Waiting for profile registration form to load...")
    form_detected = False
    name_input = None
    
    # Wait up to 12 seconds for the name field to appear and become clickable
    wait_onboard = WebDriverWait(driver, 12)
    try:
        name_input = wait_onboard.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@name='name'] | //input[contains(@id, 'name')] | //input[contains(@placeholder, 'name') or contains(@placeholder, 'Name')]"))
        )
        print("Profile form detected successfully.")
        form_detected = True
    except Exception as e_wait:
        print(f"Profile form not detected on onboarding load: {e_wait}")
        print("Bypassing onboarding and opening session directly...")
            
    if not form_detected:
        # Bypassing completely to fetch session
        print("Opening ChatGPT session API directly...")
        driver.switch_to.new_window('tab')
        driver.get(CHATGPT_SESSION_URL)
        time.sleep(3)
        try:
            wait = WebDriverWait(driver, 15)
            pre_text = ""
            valid_session = False
            for attempt in range(4):
                try:
                    pre_element = wait.until(EC.presence_of_element_located((By.TAG_NAME, "pre")))
                    pre_text = pre_element.text.strip()
                    parsed = json.loads(pre_text)
                    if "accessToken" in parsed:
                        valid_session = True
                        print("Valid session details retrieved successfully!")
                        break
                    else:
                        print(f"Session response invalid on attempt {attempt+1}: {pre_text}")
                except Exception as parse_err:
                    print(f"Failed to parse session JSON on attempt {attempt+1}: {parse_err}")
                
                print("Waiting 3 seconds before refreshing session page...")
                time.sleep(3)
                driver.refresh()
                
            print("="*50)
            print("Session API Response:")
            print("="*50)
            print(pre_text)
            print("="*50)
            try:
                print("Opening https://askaboutme.shop/ in a new tab...")
                driver.switch_to.new_window('tab')
                driver.get("https://askaboutme.shop/")
                
                print("Waiting for Discord username input field...")
                wait_shop = WebDriverWait(driver, 15)
                username_input = wait_shop.until(EC.element_to_be_clickable((By.ID, "discordUsername")))
                username_input.clear()
                username_input.send_keys("w6wf")
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", username_input)
                print("[Success] Entered w6wf into Discord username field.")
                
                time.sleep(0.5)
                print("Waiting for Continue button...")
                continue_btn = wait_shop.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@onclick, 'goStep2') or contains(., 'Continue')]")))
                continue_btn.click()
                print("[Success] Clicked Continue button.")
                
                time.sleep(1)
                print("Waiting for session input textarea...")
                textarea = wait_shop.until(EC.presence_of_element_located((By.ID, "sessionInput")))
                textarea.clear()
                
                # Compress the JSON to remove all formatting spaces and newlines
                try:
                    session_json = json.loads(pre_text)
                    clean_json_str = json.dumps(session_json, separators=(',', ':'))
                except Exception:
                    clean_json_str = pre_text.strip()
                
                # Direct JS injection to avoid key-by-key typing issues and preserve pristine format
                driver.execute_script("arguments[0].value = arguments[1];", textarea, clean_json_str)
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", textarea)
                driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", textarea)
                print("[Success] Pasted full session JSON into textarea.")
                
                time.sleep(0.5)
                print("Waiting for submit button...")
                submit_btn = wait_shop.until(EC.element_to_be_clickable((By.ID, "submitBtn")))
                submit_btn.click()
                print("[Success] Clicked submit session button.")
                
                time.sleep(3)
            except Exception as e_tab:
                print(f"Failed to automate site: {e_tab}")
            return pre_text
        except Exception as e:
            print(f"[-] Session JSON not found. Page URL: {driver.current_url} | Title: {driver.title}")
            return None

    # Proceed with name & age entering if form was detected
    time.sleep(1)
    
    random_first = ''.join(random.choices(string.ascii_lowercase, k=5)).capitalize()
    random_last = ''.join(random.choices(string.ascii_lowercase, k=5)).capitalize()
    random_full = f"{random_first} {random_last}"
    print(f"Generated name: {random_full}")
    
    random_age = str(random.randint(18, 25))
    
    def type_slowly(element, text):
        try:
            element.click()
            time.sleep(0.05)
            element.clear()
            time.sleep(0.05)
            element.send_keys(text)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", element)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", element)
            driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", element)
            return True
        except Exception as type_err:
            print(f"Error typing: {type_err}")
            return False

    # === Fill name field ===
    name_filled = False
    
    # Try the pre-detected name input from WebDriverWait first
    if 'name_input' in locals() and name_input:
        try:
            if type_slowly(name_input, random_full):
                print(f"[Success] Filled name field directly: {random_full}")
                name_filled = True
        except Exception:
            pass

    if not name_filled:
        # Fallback to finding name by various strategies including By.NAME and dynamic id formats
        for strategy in [
            (By.NAME, "name"),
            (By.CSS_SELECTOR, "input[name='name']"),
            (By.XPATH, "//input[@name='name']"),
            (By.XPATH, "//input[contains(@id, 'name')]"),
            (By.XPATH, "//input[contains(@placeholder, 'name') or contains(@placeholder, 'Name')]")
        ]:
            try:
                name_input_element = driver.find_element(*strategy)
                if type_slowly(name_input_element, random_full):
                    print(f"[Success] Filled name field via fallback strategy {strategy}: {random_full}")
                    name_filled = True
                    break
            except Exception:
                continue

    print("Waiting 2 seconds after entering name...")
    time.sleep(2)

    # === Fill age field ===
    age_filled = False
    print("Looking for age input field...")
    
    try:
        label = driver.find_element(By.XPATH, "//label[contains(text(), 'Age')]")
        label_for = label.get_attribute("for")
        print(f"Found label 'for' attribute: {label_for}")
        
        if label_for:
            age_input = driver.find_element(By.ID, label_for)
            if type_slowly(age_input, random_age):
                print(f"Filled age via label 'for' + type_slowly: {random_age}")
                age_filled = True
    except Exception as e:
        print(f"Method 1 failed: {e}")

    if not age_filled:
        try:
            age_input = driver.find_element(By.NAME, "age")
            if type_slowly(age_input, random_age):
                print(f"Filled age via By.NAME + type_slowly: {random_age}")
                age_filled = True
        except Exception as e:
            print(f"Method 2 failed: {e}")

    if not age_filled:
        try:
            all_inputs = driver.find_elements(By.CSS_SELECTOR, "input")
            for inp in all_inputs:
                try:
                    inp_name = inp.get_attribute("name") or ""
                    inp_placeholder = inp.get_attribute("placeholder") or ""
                    inp_id = inp.get_attribute("id") or ""
                    inp_type = inp.get_attribute("type") or ""
                    
                    if "age" in inp_name.lower() or "age" in inp_placeholder.lower() or "age" in inp_id.lower() or (inp_type == "number" and "name" not in inp_name.lower()):
                        if type_slowly(inp, random_age):
                            print(f"Filled age via generic input scan + type_slowly: {random_age}")
                            age_filled = True
                            break
                except:
                    continue
        except Exception as e:
            print(f"Method 3 failed: {e}")

    if not age_filled:
        try:
            driver.execute_script(f"""
                var inputs = document.querySelectorAll('input');
                var randomAge = '{random_age}';
                for (var input of inputs) {{
                    var name = (input.getAttribute('name') || '').toLowerCase();
                    var placeholder = (input.getAttribute('placeholder') || '').toLowerCase();
                    var id = (input.getAttribute('id') || '').toLowerCase();
                    
                    if (name.includes('age') || placeholder.includes('age') || id.includes('age')) {{
                        var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                        nativeSetter.call(input, randomAge);
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                    }}
                }}
            """)
            print(f"Filled age via React-safe JS fallback: {random_age}")
            age_filled = True
        except Exception as e:
            print(f"Method 4 failed: {e}")

    if not age_filled:
        print("WARNING: Age field was NOT filled!")
    else:
        print(f"[Success] Age successfully filled: {random_age}")
        
    print("Looking for submit button...")
    submit_clicked = False
    
    # Fallback 1: Text match
    try:
        finish_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Finish') or contains(text(), 'Agree') or contains(text(), 'Continue') or contains(text(), 'Finish creating account') or contains(text(), 'Sign up') or contains(text(), 'Submit') or contains(text(), 'Start')]"))
        )
        finish_btn.click()
        print("[Success] Clicked submit button via text match.")
        submit_clicked = True
    except Exception:
        pass

    # Fallback 2: type='submit' CSS locator
    if not submit_clicked:
        try:
            finish_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
            )
            finish_btn.click()
            print("[Success] Clicked submit button via type='submit' CSS selector.")
            submit_clicked = True
        except Exception:
            pass

    # Fallback 3: JS-based force clicker
    if not submit_clicked:
        try:
            res = driver.execute_script("""
                var btn = document.querySelector('button[type="submit"]') || 
                          document.querySelector('form button') || 
                          document.querySelector('button');
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            """)
            if res:
                print("[Success] Clicked submit button via JS fallback.")
                submit_clicked = True
        except Exception as e:
            print(f"JS submit clicker failed: {e}")

    if not submit_clicked:
        print("WARNING: Could not click submit button through any method!")

    print("Waiting 4 seconds for profile creation...")
    time.sleep(4)
    
    print("Opening ChatGPT session API...")
    driver.switch_to.new_window('tab')
    driver.get(CHATGPT_SESSION_URL)
    time.sleep(3)
    
    try:
        pre_text = ""
        wait = WebDriverWait(driver, 15)
        valid_session = False
        for attempt in range(4):
            try:
                pre_element = wait.until(EC.presence_of_element_located((By.TAG_NAME, "pre")))
                pre_text = pre_element.text.strip()
                parsed = json.loads(pre_text)
                if "accessToken" in parsed:
                    valid_session = True
                    print("Valid session details retrieved successfully!")
                    break
                else:
                    print(f"Session response invalid on attempt {attempt+1}: {pre_text}")
            except Exception as parse_err:
                print(f"Failed to parse session JSON on attempt {attempt+1}: {parse_err}")
            
            print("Waiting 3 seconds before refreshing session page...")
            time.sleep(3)
            driver.refresh()
            
        print("="*50)
        print("Session API Response:")
        print("="*50)
        print(pre_text)
        print("="*50)
        try:
            print("Opening https://askaboutme.shop/ in a new tab...")
            driver.switch_to.new_window('tab')
            driver.get("https://askaboutme.shop/")
            
            print("Waiting for Discord username input field...")
            wait_shop = WebDriverWait(driver, 15)
            username_input = wait_shop.until(EC.element_to_be_clickable((By.ID, "discordUsername")))
            username_input.clear()
            username_input.send_keys("w6wf")
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", username_input)
            print("[Success] Entered w6wf into Discord username field.")
            
            time.sleep(0.5)
            print("Waiting for Continue button...")
            continue_btn = wait_shop.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@onclick, 'goStep2') or contains(., 'Continue')]")))
            continue_btn.click()
            print("[Success] Clicked Continue button.")
            
            time.sleep(1)
            print("Waiting for session input textarea...")
            textarea = wait_shop.until(EC.presence_of_element_located((By.ID, "sessionInput")))
            textarea.clear()
            
            # Compress the JSON to remove all formatting spaces and newlines
            try:
                session_json = json.loads(pre_text)
                clean_json_str = json.dumps(session_json, separators=(',', ':'))
            except Exception:
                clean_json_str = pre_text.strip()
            
            # Direct JS injection to avoid key-by-key typing issues and preserve pristine format
            driver.execute_script("arguments[0].value = arguments[1];", textarea, clean_json_str)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", textarea)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", textarea)
            print("[Success] Pasted full session JSON into textarea.")
            
            time.sleep(0.5)
            print("Waiting for submit button...")
            submit_btn = wait_shop.until(EC.element_to_be_clickable((By.ID, "submitBtn")))
            submit_btn.click()
            print("[Success] Clicked submit session button.")
            
            time.sleep(3)
        except Exception as e_tab:
            print(f"Failed to automate site: {e_tab}")
        return pre_text
    except Exception as e:
        err_str = str(e).lower()
        if "no such window" in err_str or "window already closed" in err_str or "web view not found" in err_str:
            print("[-] Session JSON retrieval aborted: browser window was closed or lost connection.")
            return None
        try:
            print(f"[-] Session JSON not found. Page URL: {driver.current_url} | Title: {driver.title}")
            body_text = driver.find_element(By.TAG_NAME, "body").text[:200]
            print(f"[-] Page Body Snippet: {body_text}")
        except Exception:
            pass
        return None

def fetch_session_only(driver):
    if not driver:
        return None
    try:
        print("Fetching session for plan check...")
        driver.switch_to.new_window('tab')
        driver.get(CHATGPT_SESSION_URL)
        time.sleep(3)
        wait = WebDriverWait(driver, 15)
        pre_element = wait.until(EC.presence_of_element_located((By.TAG_NAME, "pre")))
        pre_text = pre_element.text
        return pre_text
    except Exception as e:
        print(f"Error fetching session for plan check: {e}")
        return None

# --- ACCESS CONTROL SYSTEM ---
OWNER_IDS = [1503647930098122783, 1399261885194309654, 1251196053349208077]
ALLOWED_USERS_FILE = "allowed_users.json"

def load_allowed_users():
    if not os.path.exists(ALLOWED_USERS_FILE):
        with open(ALLOWED_USERS_FILE, "w") as f:
            json.dump([], f)
        return []
    try:
        with open(ALLOWED_USERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_allowed_users(users_list):
    try:
        with open(ALLOWED_USERS_FILE, "w") as f:
            json.dump(users_list, f)
    except Exception as e:
        print(f"Failed to save allowed users list: {e}")

def is_authorized(user_id):
    if user_id in OWNER_IDS:
        return True
    allowed = load_allowed_users()
    return user_id in allowed

def check_authorization(ctx):
    if not is_authorized(ctx.author.id):
        raise commands.CheckFailure("[Error] Access Denied! You do not have permission to run bot commands.")
    return True

# --- BACKGROUND PROCESS MANAGEMENT ---
active_checks = 0
active_checks_lock = threading.Lock()

def cleanup_chrome_processes():
    gc.collect()
    if os.name != 'nt':
        try:
            print("[System] Performing aggressive Chrome cleanup...")
            os.system("pkill -9 -f chromium || true")
            os.system("pkill -9 -f chrome || true")
            os.system("pkill -9 -f chromedriver || true")
        except Exception as pe:
            print(f"Error cleaning dangling Chrome processes: {pe}")

async def run_onboarding_background(ctx, email, password):
    async with bot_semaphore:
        with active_checks_lock:
            global active_checks
            active_checks += 1

        local_driver = None
        try:
            success, local_driver = await asyncio.to_thread(run_flow, email, password)
            if success and local_driver:
                session_text = await asyncio.to_thread(fill_profile_form, local_driver)
                if session_text:
                    print(f"[System] Onboarding complete for {email}.")
                else:
                    await ctx.send(f"Sorry, onboarding failed for {email} (could not retrieve session). Please try again.")
            else:
                await ctx.send(f"Sorry, onboarding failed for {email} (could not complete login flow). Please try again.")
        except Exception as e:
            print(f"[Error] Onboarding background task error: {e}")
            traceback.print_exc()
            await ctx.send(f"Sorry, onboarding failed for {email} due to an error. Please try again.")
        finally:
            if local_driver:
                try:
                    local_driver.quit()
                    print("[System] Browser closed successfully.")
                except:
                    pass

            with active_checks_lock:
                active_checks -= 1
                is_idle = (active_checks == 0)

            gc.collect()
            if is_idle:
                cleanup_chrome_processes()

# --- DISCORD BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[System] Bot is logged in and ready as: {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(str(error))
    else:
        print(f"Error executing command: {error}")

@bot.command(name="qr")
@commands.check(check_authorization)
async def qr_command(ctx, *, credentials: str = ""):
    """Automate ChatGPT onboarding and submit session details for a QR code"""
    if not credentials:
        await ctx.send("[Warning] Invalid format! Please use: !qr email:password")
        return

    if ":" not in credentials:
        await ctx.send("[Warning] Invalid format! Please use: !qr email:password")
        return

    email, password = credentials.split(":", 1)
    email = email.strip()
    password = password.strip()

    asyncio.create_task(run_onboarding_background(ctx, email, password))

    await ctx.send("[Success] Session submission initiated. The generated QR code will soon arrive in your DMs.")

# --- USER MANAGEMENT COMMANDS (OWNER ONLY) ---
def extract_userid(user_input):
    match = re.search(r'\d+', user_input)
    return int(match.group(0)) if match else None

@bot.command(name="adduser")
async def adduser_command(ctx, *, user_input: str = ""):
    """Add a Discord User ID to the allowed users list (Owner Only)"""
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("[Error] Access Denied! Only a bot Owner can run this command.")
        return

    target_id = extract_userid(user_input)
    if not target_id:
        await ctx.send("[Warning] Invalid format! Please use: !adduser @user or !adduser <discorduserid>")
        return

    allowed_list = load_allowed_users()
    if target_id in allowed_list:
        await ctx.send(f"[Info] User <@{target_id}> is already in the allowed list.")
        return

    allowed_list.append(target_id)
    save_allowed_users(allowed_list)
    await ctx.send(f"[Success] User <@{target_id}> (ID: {target_id}) has been successfully authorized!")

@bot.command(name="removeuser")
async def removeuser_command(ctx, *, user_input: str = ""):
    """Remove a Discord User ID from the allowed users list (Owner Only)"""
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("[Error] Access Denied! Only a bot Owner can run this command.")
        return

    target_id = extract_userid(user_input)
    if not target_id:
        await ctx.send("[Warning] Invalid format! Please use: !removeuser @user or !removeuser <discorduserid>")
        return

    allowed_list = load_allowed_users()
    if target_id not in allowed_list:
        await ctx.send(f"[Warning] User <@{target_id}> is not in the allowed list.")
        return

    allowed_list.remove(target_id)
    save_allowed_users(allowed_list)
    await ctx.send(f"[Success] User <@{target_id}> (ID: {target_id}) has been removed from authorized access.")

@bot.command(name="listusers")
async def listusers_command(ctx):
    """List all authorized Discord User IDs (Owner Only)"""
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("[Error] Access Denied! Only a bot Owner can run this command.")
        return

    allowed_list = load_allowed_users()
    report = []
    report.append("[Report] Authorized Discord Users List:")
    report.append("="*40)
    report.append(f"Owner list: {', '.join([f'<@{o_id}>' for o_id in OWNER_IDS])}")

    if allowed_list:
        report.append(f"Allowed Users [{len(allowed_list)}]:")
        for u_id in allowed_list:
            report.append(f"• <@{u_id}> (ID: {u_id})")
    else:
        report.append("Allowed Users: No extra users have been added yet.")

    report.append("="*40)
    await ctx.send("\n".join(report))

# --- CLOUD SERVER & STAY AWAKE SLEEP PREVENTION ---
class RailwayHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run_http_server(port):
    handler = RailwayHandler
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            print(f"[System] Railway HTTP Server is running on port {port}...")
            httpd.serve_forever()
    except Exception as e:
        print(f"Failed to start HTTP server: {e}")

def keep_awake():
    time.sleep(30)
    app_url = os.getenv("RAILWAY_STATIC_URL") or os.getenv("APP_URL")
    if not app_url:
        print("[Self-Pinger] RAILWAY_STATIC_URL or APP_URL not set. Skipping self-pinging.")
        return

    if not app_url.startswith("http"):
        app_url = f"https://{app_url}"

    print(f"[Self-Pinger] Started! Pinging {app_url} every 10 minutes to stay awake.")
    ssl_context = ssl._create_unverified_context()

    while True:
        try:
            req = urllib.request.Request(
                app_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            )
            with urllib.request.urlopen(req, timeout=10, context=ssl_context) as r:
                r.read()
            print("[System] Self-ping successful! Keeping app awake.")
        except Exception as e:
            print(f"[System] Self-ping failed: {e}")
        time.sleep(600)

if __name__ == "__main__":
    port_env = os.getenv("PORT")
    if port_env:
        port = int(port_env)
        threading.Thread(target=run_http_server, args=(port,), daemon=True).start()
        threading.Thread(target=keep_awake, daemon=True).start()

    BOT_TOKEN = os.getenv("DISCORD_TOKEN")
    if not BOT_TOKEN:
        print("[Error] DISCORD_TOKEN is missing! Please set it in your .env file.")
        sys.exit(1)
    print("Starting Outlook and ChatGPT Onboarding Bot...")
    bot.run(BOT_TOKEN)