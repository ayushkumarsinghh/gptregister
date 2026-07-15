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
import queue
import hmac
import hashlib
import struct
import base64

# --- TOTP GENERATOR ---
def get_totp(secret):
    secret = secret.replace(" ", "").upper()
    missing_padding = len(secret) % 8
    if missing_padding:
        secret += '=' * (8 - missing_padding)
    key = base64.b32decode(secret)
    t = int(time.time() // 30)
    msg = struct.pack(">Q", t)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[19] & 15
    token = (struct.unpack(">I", h[o:o+4])[0] & 0x7fffffff) % 1000000
    return f"{token:06d}"

# --- CONFIG ---
CHATGPT_SESSION_URL = "https://chatgpt.com/api/auth/session"

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

# --- PROXY CONFIGURATION ---
# Format: "http://username:password@ip:port"
PROXY_STRING = "http://sleepiness29:pmfMiEZSvK@82.47.202.20:50100"

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
    
    # Load proxy extension if proxy is set
    if PROXY_STRING:
        try:
            plugin_dir = setup_proxy_extension(PROXY_STRING)
            options.add_argument(f"--load-extension={plugin_dir}")
            print(f"[System] Proxy extension successfully injected: {PROXY_STRING.split('@')[-1]}")
        except Exception as proxy_err:
            print(f"[Warning] Failed to set up proxy extension: {proxy_err}")
            
    # Configure required container sandbox arguments in cloud/Docker environments
    is_container = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
    if is_container:
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--window-size=1920,1080")
        
        # Optimize memory usage to prevent OOM kills on Railway (512MB RAM limit)
        options.add_argument("--js-flags=--max-old-space-size=256")
        options.add_argument("--disable-features=Translate,SafeBrowsing,CalculatePageVisibilityAPI")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-sync")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--prerender-from-omnibox=disabled")
        
    return options

class DiscordBridge:
    def __init__(self, bot, ctx, email, inbox_url=None):
        self.bot = bot
        self.ctx = ctx
        self.email = email
        self.inbox_url = inbox_url
        self.loop = asyncio.get_running_loop()

    def get_otp(self):
        """Blocks the Selenium thread and waits for the user response on Discord"""
        future = asyncio.run_coroutine_threadsafe(self._async_get_otp(), self.loop)
        return future.result()

    async def _async_get_otp(self):
        msg_text = f"✉️ **OTP has been sent to `{self.email}`.**\n"
        if self.inbox_url:
            msg_text += f"📬 **Inbox Link**: {self.inbox_url}\n"
        msg_text += f"Please check your inbox and reply here with the 6-digit code, or reply `resend` to request a new code."
        await self.ctx.send(msg_text)

        def check(m):
            return m.author == self.ctx.author and m.channel == self.ctx.channel

        try:
            # Wait up to 5 minutes for user response
            msg = await self.bot.wait_for('message', check=check, timeout=300.0)
            return msg.content.strip()
        except asyncio.TimeoutError:
            await self.ctx.send("⏰ **Timeout:** No response received within 5 minutes. Aborting flow.")
            return None

    def notify_resend(self, success):
        asyncio.run_coroutine_threadsafe(self._async_notify_resend(success), self.loop)

    async def _async_notify_resend(self, success):
        if success:
            await self.ctx.send("🔄 **Resend requested successfully!** Waiting for your new 6-digit OTP code...")
        else:
            await self.ctx.send("⚠️ **Resend request failed.** Try entering the code manually.")

    def ask_close_confirm(self):
        """Blocks the Selenium thread and asks the user whether to close the browser/session"""
        future = asyncio.run_coroutine_threadsafe(self._async_ask_close_confirm(), self.loop)
        return future.result()

    async def _async_ask_close_confirm(self):
        await self.ctx.send(
            f"🔄 **Session extracted for `{self.email}`.**\n"
            f"Should we close the browser session? Reply **`yes`** to close it, or **`no`** to leave it running."
        )

        def check(m):
            return m.author == self.ctx.author and m.channel == self.ctx.channel

        while True:
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=300.0)
                content = msg.content.strip().lower()
                if content in ['yes', 'y', 'close', 'true']:
                    return True
                elif content in ['no', 'n', 'false', 'keep']:
                    return False
                else:
                    await self.ctx.send("⚠️ Please reply **`yes`** to close the session, or **`no`** to keep it running.")
            except asyncio.TimeoutError:
                # Still waiting indefinitely, ping user that it is still active
                await self.ctx.send(f"⏳ **Still waiting:** Browser session for `{self.email}` is still active. Close it? (Reply **`yes`** / **`no`**)")
            
    def send_log(self, text):
        asyncio.run_coroutine_threadsafe(self.ctx.send(text), self.loop)

    def send_file(self, file_path, content=None):
        asyncio.run_coroutine_threadsafe(self._async_send_file(file_path, content), self.loop)

    async def _async_send_file(self, file_path, content=None):
        if os.path.exists(file_path):
            try:
                file = discord.File(file_path)
                await self.ctx.send(content=content, file=file)
            except Exception as e:
                print(f"Failed to send file {file_path} to Discord: {e}")

def fetch_otp_from_inbox(driver, inbox_url, exclude_otp=None, max_wait=300, bridge=None):
    original_window = driver.current_window_handle
    
    # Open new tab and navigate to inbox_url
    driver.execute_script("window.open(arguments[0], '_blank');", inbox_url)
    time.sleep(1)
    
    # Switch to the new tab
    new_window = [w for w in driver.window_handles if w != original_window][-1]
    driver.switch_to.window(new_window)
    
    otp_code = None
    start_time = time.time()
    
    if bridge:
        bridge.send_log(f"[*] Opened inbox tab: waiting for verification code...")
        
    while time.time() - start_time < max_wait:
        try:
            # Find <p> tags with 6-digit text
            elements = driver.find_elements(By.TAG_NAME, "p")
            for el in elements:
                txt = el.text.strip()
                txt_clean = re.sub(r'\s+', '', txt)
                if txt_clean.isdigit() and len(txt_clean) == 6:
                    if exclude_otp and txt_clean == exclude_otp:
                        continue
                    otp_code = txt_clean
                    break
            
            if otp_code:
                if bridge:
                    bridge.send_log(f"[+] Found verification code: {otp_code}")
                break
        except Exception as e:
            print(f"[OTP Fetch] Error: {e}")
            
        time.sleep(4)
        try:
            driver.refresh()
        except:
            pass
            
    # Close inbox tab and switch back
    try:
        driver.close()
    except:
        pass
    driver.switch_to.window(original_window)
    return otp_code

def run_flow(email, bridge):
    max_retries = 3
    retry_count = 0
    last_driver = None

    while retry_count < max_retries:
        driver = create_driver()
        wait = WebDriverWait(driver, 30)
        last_driver = driver

        try:
            bridge.send_log("[*] Navigating to ChatGPT...")
            driver.get('https://chatgpt.com/')
            
            time.sleep(1)
            current_url = driver.current_url.lower()
            
            # Click ChatGPT login button
            chatgpt_login_btn = None
            try:
                chatgpt_login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='login-button']")))
            except Exception:
                try:
                    chatgpt_login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Log in') or contains(text(), 'Login')]")))
                except Exception:
                    try:
                        chatgpt_login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Log in') or contains(text(), 'Login')]")))
                    except Exception:
                        pass
            
            if not chatgpt_login_btn:
                chatgpt_login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='login-button']")))
                
            chatgpt_login_btn.click()
            bridge.send_log("[*] Clicked Log in button.")
            
            # Enter email
            chatgpt_email_input = wait.until(EC.element_to_be_clickable((By.ID, "email")))
            chatgpt_email_input.clear()
            chatgpt_email_input.send_keys(email)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", chatgpt_email_input)
            
            # Submit email
            chatgpt_continue_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']")))
            chatgpt_continue_btn.click()
            bridge.send_log("[*] Submitted email address.")
            
            # OTP prompt loop
            first_otp = None
            last_tried_otp = None
            while True:
                if bridge.inbox_url:
                    otp = fetch_otp_from_inbox(driver, bridge.inbox_url, exclude_otp=last_tried_otp, bridge=bridge)
                    if not otp:
                        raise Exception("Failed to retrieve OTP from inbox URL.")
                    last_tried_otp = otp
                else:
                    otp = bridge.get_otp()
                    if not otp:
                        raise Exception("OTP prompt timed out or cancelled by user.")
                
                if not first_otp:
                    first_otp = otp
                
                if otp.lower() == 'resend':
                    bridge.send_log("[*] Requesting resend of email verification code...")
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
                        bridge.notify_resend(True)
                    else:
                        bridge.notify_resend(False)
                    continue
                
                try:
                    # Fetch fresh code_input locator on every iteration to avoid stale element reference exceptions
                    code_input = wait.until(EC.element_to_be_clickable((By.NAME, "code")))
                    code_input.click()
                    time.sleep(0.5)
                    code_input.clear()
                    time.sleep(0.5)
                    
                    # Type OTP slowly character-by-character to mimic human behavior
                    for digit in otp:
                        code_input.send_keys(digit)
                        time.sleep(random.uniform(0.3, 0.7))
                        
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", code_input)
                    time.sleep(1.2)
                    
                    verify_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[name='intent'][value='validate']")))
                    try:
                        verify_btn.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", verify_btn)
                    
                    # Verify redirection (allow onboarding pages like chatgpt.com/auth/onboarding to pass)
                    WebDriverWait(driver, 60).until(
                        lambda d: "chatgpt.com" in d.current_url.lower() and 
                                  "auth.openai.com" not in d.current_url.lower() and 
                                  "auth0.openai.com" not in d.current_url.lower() and 
                                  "auth/login" not in d.current_url.lower()
                    )
                    bridge.send_log("[+] Login validated successfully!")
                    time.sleep(3)
                    break
                except Exception as loop_err:
                    # Check if driver is disconnected/dead
                    try:
                        driver.title
                    except Exception:
                        print("Chrome driver disconnected. Propagating error to restart browser.")
                        raise loop_err
 
                    try:
                        current_url = driver.current_url
                        page_title = driver.title
                        # Also take a fresh screenshot on validation failure to debug
                        driver.save_screenshot("flow_error_debug.png")
                    except:
                        current_url = "unknown"
                        page_title = "unknown"
                    msg = f"❌ **Validation Failed:** Invalid code or validation timeout.\n* **URL**: `{current_url}`\n* **Title**: `{page_title}`\nPlease try again."
                    if os.path.exists("flow_error_debug.png"):
                        bridge.send_file("flow_error_debug.png", content=msg)
                        try:
                            os.remove("flow_error_debug.png")
                        except:
                            pass
                    else:
                        bridge.send_log(msg)
            
            return True, driver, first_otp
            
        except Exception as e:
            print(f"Flow attempt {retry_count+1} failed:")
            traceback.print_exc()
            if driver:
                try:
                    driver.save_screenshot("flow_error_debug.png")
                    print("[Debug] Saved error state screenshot as flow_error_debug.png")
                except Exception as ss_err:
                    print(f"Failed to save error screenshot: {ss_err}")
            err_msg = str(e)
            if "OTP prompt timed out" in err_msg:
                # User did not reply, abort immediately
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                return False, None, None
 
            retry_count += 1
            if driver:
                try:
                    driver.quit()
                except:
                    pass
                driver = None
            if retry_count < max_retries:
                bridge.send_log(f"[*] Attempt {retry_count} failed. Restarting browser flow...")
                time.sleep(3)
                continue
            else:
                break
                
    return False, None, None

def create_driver(options=None):
    is_headless = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
    try:
        print(f"Initializing Chrome driver (auto-detect) | Headless: {is_headless}...")
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

def fill_profile_form(driver, inbox_url=None, first_otp=None, bridge=None):
    mfa_secret = None
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
            return pre_text, None
        except Exception as e:
            print(f"[-] Session JSON not found. Page URL: {driver.current_url} | Title: {driver.title}")
            return None, None

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
    
    # === Add Password settings flow ===
    try:
        print("[Security] Navigating to Security settings page...")
        driver.get("https://chatgpt.com/#settings/Security")
        time.sleep(4)
        
        wait_sec = WebDriverWait(driver, 15)
        
        # Click "Add Password" button
        pass_btn = wait_sec.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='password-setting']")))
        try:
            pass_btn.click()
        except:
            driver.execute_script("arguments[0].click();", pass_btn)
        print("[Security] Clicked password-setting button.")
        time.sleep(3)
        
        # Wait for the verification code input
        code_input = wait_sec.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[placeholder='Code'], input[name='code']")))
        print("[Security] Found identity verification code input for password addition.")
        
        # Get the new OTP code (excluding the first login OTP)
        if inbox_url:
            new_otp = fetch_otp_from_inbox(driver, inbox_url, exclude_otp=first_otp, bridge=bridge)
        else:
            if bridge:
                new_otp = bridge.get_otp()
            else:
                new_otp = None
                
        if not new_otp:
            raise Exception("Verification code for password setup not provided/found.")
            
        # Enter verification code
        for digit in new_otp:
            code_input.send_keys(digit)
            time.sleep(random.uniform(0.1, 0.3))
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", code_input)
        time.sleep(1.5)
        
        # Click Continue to verify identity
        continue_btn = wait_sec.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[name='intent'][value='validate'], button[data-dd-action-name='Continue']")))
        try:
            continue_btn.click()
        except:
            driver.execute_script("arguments[0].click();", continue_btn)
        print("[Security] Clicked verification Continue button.")
        time.sleep(4)
        
        # Wait for password input fields
        new_pass_input = wait_sec.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='new-password']")))
        confirm_pass_input = wait_sec.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='confirm-password']")))
        
        password_to_set = "SLEEPYYY12177"
        
        # Type password
        new_pass_input.clear()
        new_pass_input.send_keys(password_to_set)
        confirm_pass_input.clear()
        confirm_pass_input.send_keys(password_to_set)
        
        # Dispatch input events
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", new_pass_input)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", confirm_pass_input)
        time.sleep(2)
        
        # Click Continue to save the password
        submit_pass_btn = wait_sec.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit'][data-dd-action-name='Continue']")))
        try:
            submit_pass_btn.click()
        except:
            driver.execute_script("arguments[0].click();", submit_pass_btn)
        print("[Security] Clicked password save Continue button.")
        time.sleep(4)
        print("[Security] Password setup completed successfully.")
        
    except Exception as sec_e:
        print(f"[Security Error] Failed to set password: {sec_e}")
        try:
            driver.save_screenshot("security_flow_error.png")
            if bridge:
                bridge.send_file("security_flow_error.png", content=f"⚠️ **Security Setup Failed:** {sec_e}")
                os.remove("security_flow_error.png")
        except:
            pass

    # === Enable Multi-Factor Authentication (MFA) ===
    try:
        print("[MFA] Initializing Multi-Factor Authentication setup...")
        # Reload/navigate to settings to close modal and start fresh
        driver.get("https://chatgpt.com/#settings/Security")
        time.sleep(4)
        
        wait_sec = WebDriverWait(driver, 15)
        
        # Toggle MFA switch
        mfa_toggle = wait_sec.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='mfa-authenticator-toggle']"))
        )
        try:
            mfa_toggle.click()
        except:
            driver.execute_script("arguments[0].click();", mfa_toggle)
        print("[MFA] Clicked MFA authenticator toggle.")
        time.sleep(3)
        
        # Click "Trouble scanning?" button
        trouble_btn = wait_sec.until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Trouble scanning?')]"))
        )
        try:
            trouble_btn.click()
        except:
            driver.execute_script("arguments[0].click();", trouble_btn)
        print("[MFA] Clicked 'Trouble scanning?' button.")
        time.sleep(2)
        
        # Extract 2FA secret code
        secret_div = wait_sec.until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='button' and (@aria-label='Copy code' or @title='Copy code' or contains(text(), 'Copy code'))]"))
        )
        mfa_secret = secret_div.text.strip()
        print(f"[MFA] Extracted secret key: {mfa_secret}")
        
        # Generate 6-digit TOTP code locally in Python
        totp_code = get_totp(mfa_secret)
        print(f"[MFA] Generated 6-digit TOTP code: {totp_code}")
        
        # Locate TOTP code input field
        totp_input = wait_sec.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='totp_otp'], input[id='totp_otp']"))
        )
        totp_input.clear()
        totp_input.send_keys(totp_code)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", totp_input)
        time.sleep(1.5)
        
        # Click Verify button
        verify_btn = wait_sec.until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Verify')]"))
        )
        try:
            verify_btn.click()
        except:
            driver.execute_script("arguments[0].click();", verify_btn)
        print("[MFA] Clicked Verify button.")
        time.sleep(4)
        print("[MFA] Multi-Factor Authentication setup completed successfully!")
        
    except Exception as mfa_e:
        print(f"[MFA Error] Failed to set up MFA: {mfa_e}")
        try:
            driver.save_screenshot("mfa_flow_error.png")
            if bridge:
                bridge.send_file("mfa_flow_error.png", content=f"⚠️ **MFA Setup Failed:** {mfa_e}")
                os.remove("mfa_flow_error.png")
        except:
            pass

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
        return pre_text, mfa_secret
    except Exception as e:
        err_str = str(e).lower()
        if "no such window" in err_str or "window already closed" in err_str or "web view not found" in err_str:
            print("[-] Session JSON retrieval aborted: browser window was closed or lost connection.")
            return None, mfa_secret
        try:
            print(f"[-] Session JSON not found. Page URL: {driver.current_url} | Title: {driver.title}")
            body_text = driver.find_element(By.TAG_NAME, "body").text[:200]
            print(f"[-] Page Body Snippet: {body_text}")
        except Exception:
            pass
        return None, mfa_secret

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
    return True

# --- BACKGROUND PROCESS MANAGEMENT ---
active_checks = 0
active_checks_lock = threading.Lock()
active_drivers = {}
active_drivers_lock = threading.Lock()

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

async def run_onboarding_background(ctx, bot, email, inbox_url=None):
    async with bot_semaphore:
        with active_checks_lock:
            global active_checks
            active_checks += 1

        local_driver = None
        bridge = DiscordBridge(bot, ctx, email, inbox_url)
        try:
            success, local_driver, first_otp = await asyncio.to_thread(run_flow, email, bridge)
            if success and local_driver:
                with active_drivers_lock:
                    active_drivers[email] = local_driver
                
                session_text, mfa_secret = await asyncio.to_thread(fill_profile_form, local_driver, inbox_url, first_otp, bridge)
                if session_text:
                    bridge.send_log(f"[System] Onboarding complete for {email}. Compiling session data...")
                    
                    # Save session to a temp file and send it
                    filename = f"session_{email.replace('@', '_').replace('.', '_')}.txt"
                    with open(filename, "w", encoding="utf-8") as f:
                        mfa_str = mfa_secret if mfa_secret else "None"
                        f.write(f"{email}|SLEEPYYY12177|{mfa_str}\n\nSession Data:\n{session_text}")
                    
                    if os.path.exists(filename):
                        discord_file = discord.File(filename)
                        await ctx.send(content=f"✅ **Session Created Successfully!** Here is the raw ChatGPT session for `{email}`:", file=discord_file)
                        os.remove(filename)
                else:
                    screenshot_sent = False
                    if local_driver:
                        try:
                            screenshot_path = "error_screenshot.png"
                            local_driver.save_screenshot(screenshot_path)
                            if os.path.exists(screenshot_path):
                                file = discord.File(screenshot_path)
                                await ctx.send(content=f"Sorry, onboarding failed for {email} (could not retrieve session). Here is the browser state:", file=file)
                                screenshot_sent = True
                                os.remove(screenshot_path)
                        except Exception as ss_err:
                            print(f"Failed to capture debug screenshot: {ss_err}")
                    if not screenshot_sent:
                        await ctx.send(f"Sorry, onboarding failed for {email} (could not retrieve session). Please try again.")
            else:
                screenshot_sent = False
                if os.path.exists("flow_error_debug.png"):
                    try:
                        file = discord.File("flow_error_debug.png")
                        await ctx.send(content=f"Sorry, onboarding failed for {email} (could not complete login flow). Here is what the browser saw:", file=file)
                        screenshot_sent = True
                        os.remove("flow_error_debug.png")
                    except Exception as ss_err:
                        print(f"Failed to send local debug screenshot: {ss_err}")
                if not screenshot_sent:
                    await ctx.send(f"Sorry, onboarding failed for {email} (could not complete login flow). Please try again.")
        except Exception as e:
            print(f"[Error] Onboarding background task error: {e}")
            traceback.print_exc()
            screenshot_sent = False
            if os.path.exists("flow_error_debug.png"):
                try:
                    file = discord.File("flow_error_debug.png")
                    await ctx.send(content=f"Sorry, onboarding failed for {email} due to an error. Here is what the browser saw at the time of failure:", file=file)
                    screenshot_sent = True
                    os.remove("flow_error_debug.png")
                except Exception as ss_err:
                    print(f"Failed to send local debug screenshot: {ss_err}")
            if not screenshot_sent:
                await ctx.send(f"Sorry, onboarding failed for {email} due to an error. Please try again.")
            if local_driver:
                try:
                    local_driver.quit()
                    print("[System] Browser closed successfully due to error.")
                except:
                    pass
                with active_drivers_lock:
                    if email in active_drivers:
                        del active_drivers[email]
                local_driver = None
        finally:
            if local_driver:
                should_close = await asyncio.to_thread(bridge.ask_close_confirm)
                if should_close:
                    try:
                        local_driver.quit()
                        print("[System] Browser closed successfully.")
                    except:
                        pass
                else:
                    print("[System] Keeping browser running as requested by user.")
                
                with active_drivers_lock:
                    if email in active_drivers:
                        del active_drivers[email]

            with active_checks_lock:
                active_checks -= 1
                is_idle = (active_checks == 0)

            gc.collect()
            if is_idle:
                cleanup_chrome_processes()

# --- DISCORD BOT SETUP ---
intents = discord.Intents.all()
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

@bot.command(name="session")
async def session_command(ctx, *, email_input: str = ""):
    """Automate ChatGPT onboarding and export session details inside a .txt file"""
    if not email_input:
        await ctx.send("[Warning] Invalid format! Please use: !session email|inbox_url")
        return

    email_input = email_input.strip()
    inbox_url = None
    if "|" in email_input:
        parts = email_input.split("|", 1)
        email = parts[0].strip()
        inbox_url = parts[1].strip()
    else:
        email = email_input

    asyncio.create_task(run_onboarding_background(ctx, bot, email, inbox_url))
    await ctx.send(f"[Success] Session process initiated for `{email}`. Follow instructions below for OTP...")

@bot.command(name="close")
async def close_command(ctx, *, email: str = ""):
    """Force close a running ChatGPT browser session. If no email is provided, closes all active browser sessions."""
    email = email.strip()
    
    if not email:
        closed_count = 0
        with active_drivers_lock:
            emails_to_close = list(active_drivers.keys())
            for email_key in emails_to_close:
                driver = active_drivers[email_key]
                try:
                    driver.quit()
                    closed_count += 1
                except Exception as e:
                    print(f"Failed to quit driver for {email_key} on !close: {e}")
                del active_drivers[email_key]
        if closed_count > 0:
            await ctx.send(f"✅ **Closed all active browser sessions ({closed_count} total).**")
        else:
            await ctx.send("❌ **No active browser sessions found to close.**")
        return
        
    closed = False
    with active_drivers_lock:
        if email in active_drivers:
            driver = active_drivers[email]
            try:
                driver.quit()
                closed = True
            except Exception as e:
                print(f"Failed to quit driver on !close for {email}: {e}")
            del active_drivers[email]
            
    if closed:
        await ctx.send(f"✅ **Browser session for `{email}` has been forced closed successfully.**")
    else:
        await ctx.send(f"❌ **No active browser session found for `{email}`.**")

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

import subprocess

if __name__ == "__main__":
    # Programmatically spawn Xvfb inside the container for headful Turnstile bypasses without xvfb-run wrapper hangs
    is_container = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
    if is_container:
        try:
            print("[System] Starting virtual display Xvfb in background...", flush=True)
            subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24", "-ac"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.environ["DISPLAY"] = ":99"
            print("[System] Virtual display Xvfb successfully initialized on display :99.", flush=True)
        except Exception as xvfb_err:
            print(f"[Warning] Failed to start background Xvfb: {xvfb_err}", flush=True)

    port_env = os.getenv("PORT")
    if port_env:
        port = int(port_env)
        threading.Thread(target=run_http_server, args=(port,), daemon=True).start()
        threading.Thread(target=keep_awake, daemon=True).start()

    BOT_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")
    
    if not BOT_TOKEN:
        print("[Error] No BOT_TOKEN or DISCORD_TOKEN found in environment variables! Please set it before running the bot.", flush=True)
        sys.exit(1)
        
    # Mask and log the loaded token for verification
    masked_token = BOT_TOKEN[:10] + "..." if len(BOT_TOKEN) > 10 else BOT_TOKEN
    print(f"[System] Bot Token successfully loaded: {masked_token}", flush=True)
    print("Starting Outlook and ChatGPT Onboarding Bot...", flush=True)
    bot.run(BOT_TOKEN)