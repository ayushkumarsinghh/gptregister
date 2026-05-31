import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time
import random
import string
import json
import os
import re
import discord
from discord.ext import commands
import asyncio
import traceback
import threading
import http.server
import socketserver
import ssl
import urllib.request
import gc
# Load standard .env file manually if it exists
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

# --- CONFIG ---
URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=9199bf20-a13f-4107-85dc-02114787ef48&scope=https%3A%2F%2Foutlook.office.com%2F.default%20openid%20profile%20offline_access&redirect_uri=https%3A%2F%2Foutlook.live.com%2Fmail%2F&client-request-id=85af84fb-4838-c204-f618-76e540231109&response_mode=fragment&client_info=1&prompt=select_account&nonce=019e35f5-4ebc-7f28-8e36-611bb37f46ef&state=eyJpZCI6IjAxOWUzNWY1LTRlYmItNzdmZS04MzkwLTVlMmMzZTFhN2FiMiIsIm1ldGEiOnsiaW50ZXJhY3Rpb25UeXBlIjoicmVkaXJlY3QifX0%3D%7CaHR0cHM6Ly9vdXRsb29rLmxpdmUuY29tL21haWwvP2N1bHR1cmU9ZW4tdXMmY291bnRyeT11Uw&claims=%7B%22access_token%22%3A%7B%22xms_cc%22%3A%7B%22values%22%3A%5B%22CP1%22%5D%7D%7D%7D&x-client-SKU=msal.js.browser&x-client-VER=4.28.2&response_type=code&code_challenge=Y-gIvtWec47bQ-tJO49QiNIoRYFseu5HdBprFFN3Af0&code_challenge_method=S256&cobrandid=ab0455a0-8d03-46b9-b18b-df2f57b9e44c&fl=dob,flname,wld&sso_reload=true"

db_write_lock = threading.Lock()
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_CHECKS", "3"))
bot_semaphore = asyncio.Semaphore(MAX_CONCURRENT)

active_checks = 0
active_checks_lock = threading.Lock()

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

# --- HEADLESS CHROMEDRIVER OPTIONS FACTORY ---
def get_chrome_options():
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    is_cloud = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
    if is_cloud:
        # options.add_argument("--headless=new")  # Handled in uc.Chrome constructor
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-default-apps")
        options.add_argument("--no-first-run")
        options.add_argument("--no-service-autorun")
        options.add_argument("--password-store=basic")
        options.add_argument("--use-gl=swiftshader")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("--js-flags=--max-old-space-size=256")
        options.add_argument("--no-zygote")
        options.add_argument("--disable-renderer-backgrounding")
    return options

import gc

def cleanup_chrome_processes():
    # Force Python to release memory immediately
    gc.collect()

    is_cloud = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
    if is_cloud:
        try:
            # Force kill any dangling or zombie chromium processes owned by the user when idle
            print("[System] All active checking sessions complete. Performing aggressive Chrome cleanup...")
            os.system("pkill -9 -f chromium || true")
            os.system("pkill -9 -f chrome || true")
            os.system("pkill -9 -f chromedriver || true")
        except Exception as pe:
            print(f"Error cleaning dangling Chrome processes: {pe}")

def create_driver(options=None):
    is_cloud = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
    # Try auto-detect first
    try:
        print("Initializing Chrome driver (auto-detect)...")
        fresh_options = get_chrome_options()
        return uc.Chrome(options=fresh_options, headless=is_cloud, use_subprocess=True)
    except Exception as e:
        err_msg = str(e)
        print(f"Auto-detect failed: {err_msg}")
        
        # Self-healing: Parse version aggressively from error message
        # Handled cases: "This version of ChromeDriver only supports Chrome version XX" OR "Current browser version is XX.X.X"
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
            
        # If we failed to get it from error but we are on Linux, try finding it via command line
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
                return uc.Chrome(options=retry_options, version_main=detected_ver, headless=is_cloud, use_subprocess=True)
            except Exception as retry_err:
                print(f"Self-Healing retry failed for version {detected_ver}: {retry_err}")

        # On Windows, try registry lookup
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
                    return uc.Chrome(options=reg_options, version_main=major_version, headless=is_cloud, use_subprocess=True)
                except Exception as reg_err:
                    print(f"Failed with version_main={major_version}: {reg_err}")

        # Fallback to common versions (including 148, 147, 149)
        for ver in [148, 147, 149, 146]:
            try:
                print(f"Initializing Chrome driver with fallback version_main={ver}...")
                fallback_options = get_chrome_options()
                return uc.Chrome(options=fallback_options, version_main=ver, headless=is_cloud, use_subprocess=True)
            except Exception:
                pass

        # If all else fails, try one last time with auto-detect to let the error propagate
        print("All Chrome driver initialization attempts failed. Trying final fallback...")
        final_options = get_chrome_options()
        return uc.Chrome(options=final_options, headless=is_cloud, use_subprocess=True)

# --- SELENIUM WORKERS ---

def fetch_otp_from_outlook(email, password):
    options = get_chrome_options()
    driver = create_driver(options)
        
    wait = WebDriverWait(driver, 35)
    
    try:
        driver.get(URL)
        print("Navigated to Outlook login page.")
        
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
            
        print("Outlook logged in. Searching for ChatGPT verification code using py3.py logic...")
        time.sleep(3)
        
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
            print("Email not clicked yet. Opening topmost email as fallback...")
            try:
                top_email = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")))
                top_email.click()
                print("Clicked TOPMOST email fallback!")
                chatgpt_email_found = True
            except Exception as top_err:
                print(f"Failed to click topmost email: {top_err}")
                
        print("Monitoring for OpenAI verification codes in email body (py3.py logic)...")
        time.sleep(4)
        
        start_time = time.time()
        while time.time() - start_time < 120:
            try:
                code_to_enter = None
                
                # Style-based Menlo/Monaco scanning
                try:
                    elements = driver.find_elements(By.XPATH, "//*[contains(@style, 'Menlo') or contains(@style, 'Monaco') or contains(@style, 'F3F3F3')]")
                    for elem in elements:
                        text = elem.text.strip()
                        if len(text) == 6 and text.isdigit():
                            code_to_enter = text
                            print(f"Copied code from styled element: {code_to_enter}")
                            return code_to_enter, driver
                except Exception:
                    pass
                
                # Pre-extracted preview code check
                if not code_to_enter and extracted_code:
                    code_to_enter = extracted_code
                    print(f"Using pre-extracted code: {code_to_enter}")
                    return code_to_enter, driver
                
                # General body parsing fallback
                if not code_to_enter:
                    try:
                        page_text = driver.find_element(By.TAG_NAME, "body").text
                        match = re.search(r'(?:continue|code):\s*(\d{6})', page_text, re.IGNORECASE)
                        if match:
                            code_to_enter = match.group(1)
                            return code_to_enter, driver
                        else:
                            matches = re.findall(r'\b\d{6}\b', page_text)
                            if matches:
                                code_to_enter = matches[0]
                                return code_to_enter, driver
                    except Exception:
                        pass
            except Exception as e:
                print("Error during code checking cycle:", e)
            
            time.sleep(3)
            
        return None, driver
    except Exception as e:
        print(f"OTP extraction failed: {e}")
        return None, driver


def check_chatgpt_plus_in_outlook(email, password):
    options = get_chrome_options()
    driver = create_driver(options)
        
    wait = WebDriverWait(driver, 35)
    
    try:
        driver.get(URL)
        
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
            
        print("Outlook logged in. Searching for subscription / invoice keywords...")
        time.sleep(3)
        
        search_input = wait.until(EC.element_to_be_clickable((By.ID, "topSearchInput")))
        search_input.click()
        search_input.send_keys(Keys.CONTROL + "a")
        search_input.send_keys(Keys.BACKSPACE)
        search_input.send_keys("chatgpt plus")
        search_input.send_keys("\n")
        time.sleep(4)
        
        items = driver.find_elements(By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")
        if items:
            for item in items[:10]:
                text = (item.text or "").lower()
                aria_label = (item.get_attribute("aria-label") or "").lower()
                combined_text = text + " " + aria_label
                if "chatgpt plus" in combined_text or "subscription" in combined_text or "receipt" in combined_text or "invoice" in combined_text or "payment" in combined_text:
                    return "Subscribed", driver
                    
        # Secondary check
        search_input = wait.until(EC.element_to_be_clickable((By.ID, "topSearchInput")))
        search_input.click()
        search_input.send_keys(Keys.CONTROL + "a")
        search_input.send_keys(Keys.BACKSPACE)
        search_input.send_keys("openai subscription")
        search_input.send_keys("\n")
        time.sleep(4)
        
        items = driver.find_elements(By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")
        if items:
            for item in items[:10]:
                text = (item.text or "").lower()
                aria_label = (item.get_attribute("aria-label") or "").lower()
                combined_text = text + " " + aria_label
                if "openai" in combined_text and ("subscription" in combined_text or "payment" in combined_text or "receipt" in combined_text or "invoice" in combined_text or "plus" in combined_text):
                    return "Subscribed", driver
                    
        return "Not Subscribed", driver
    except Exception as e:
        print(f"Check failed: {e}")
        return f"Error: {str(e).splitlines()[0]}", driver





# --- DATABASE CONFIG ---
DB_FILE = "buydb.json"
DONE_LOG_CHANNEL = 1507918067772948500

def load_db():
    with db_write_lock:
        if not os.path.exists(DB_FILE):
            default = {
                "balances": {},
                "assigned": {},
                "done_logs": {}
            }
            with open(DB_FILE, "w") as f:
                json.dump(default, f, indent=4)
            return default

        try:
            with open(DB_FILE, "r") as f:
                db = json.load(f)
        except:
            db = {}

        db.setdefault("balances", {})
        db.setdefault("assigned", {})
        db.setdefault("done_logs", {})
        return db

def save_db(data):
    with db_write_lock:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)

# --- DISCORD BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[System] Bot is logged in and ready as: {bot.user}")

def parse_multiple_credentials(user_input):
    parts = user_input.strip().split()
    accounts = []
    for p in parts:
        if ":" in p:
            email, password = p.split(":", 1)
            accounts.append((email.strip(), password.strip()))
    return accounts

def extract_userid(user_input):
    match = re.search(r'\d+', user_input)
    return int(match.group(0)) if match else None

# --- PERMISSION PROTECTION WRAPPER ---
def check_authorization(ctx):
    if not is_authorized(ctx.author.id):
        raise commands.CheckFailure("[Error] Access Denied! You do not have permission to run bot commands.")
    return True

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(str(error))
    else:
        print(f"Error executing command: {error}")

# --- USER MANAGEMENT COMMANDS (OWNER ONLY) ---
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
    await ctx.send(f"[Success] [Access Granted] User <@{target_id}> (ID: {target_id}) has been successfully authorized to run bot commands!")

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
    await ctx.send(f"[Success] [Access Revoked] User <@{target_id}> (ID: {target_id}) has been removed from authorized access.")

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

# --- PRIMARY WORKER BOT COMMANDS (PROTECTED) ---
@bot.command()
@commands.check(check_authorization)
async def done(ctx, *, data):
    db = load_db()
    uid = str(ctx.author.id)

    if ":" not in data:
        return await ctx.send("[Error] Invalid format\nUse: !done mail:pass")

    if uid not in db["assigned"]:
        db["assigned"][uid] = []

    assigned_lower = [x.lower().strip() for x in db["assigned"].get(uid, [])]
    if data.lower().strip() not in assigned_lower:
        return await ctx.send("[Error] This mail wasn't assigned to you")

    await ctx.send("[Status] Checking ChatGPT Plus...")
    email, password = data.split(":", 1)

    async with bot_semaphore:
        with active_checks_lock:
            global active_checks
            active_checks += 1

        local_driver = None
        try:
            status, local_driver = await asyncio.to_thread(check_chatgpt_plus_in_outlook, email, password)
        except Exception as e:
            print(f"Checker Error: {e}")
            return await ctx.send("[Error] Checker failed")
        finally:
            if local_driver:
                try:
                    local_driver.quit()
                except:
                    pass

            with active_checks_lock:
                active_checks -= 1
                is_idle = (active_checks == 0)

            gc.collect()
            if is_idle:
                cleanup_chrome_processes()

    if status != "Subscribed":
        return await ctx.send(f"[Failure] ChatGPT Plus not found\nStatus: {status}")

    with db_write_lock:
        db = load_db()
        if uid not in db["balances"]:
            db["balances"][uid] = 0

        db["balances"][uid] += 30
        bal = db["balances"][uid]

        for combo in db["assigned"].get(uid, []):
            if combo.lower().strip() == data.lower().strip():
                db["assigned"][uid].remove(combo)
                break

        username = str(ctx.author)
        if username not in db["done_logs"]:
            db["done_logs"][username] = []
        db["done_logs"][username].append(data)
        save_db(db)

    channel = bot.get_channel(DONE_LOG_CHANNEL)
    if channel:
        try:
            embed = discord.Embed(title="[Success] Done Submitted", color=0x00ff99)
            embed.add_field(name="User", value=ctx.author.mention, inline=False)
            embed.add_field(name="Mail", value=data, inline=False)
            embed.add_field(name="Checker Status", value=status, inline=False)
            embed.add_field(name="Balance", value=f"{bal} coins", inline=False)
            await channel.send(embed=embed)
            await channel.send(f"```{data}```")
        except Exception as log_err:
            print(f"Failed logging to channel: {log_err}")

    await ctx.send(f"[Success] ChatGPT Plus Found\nAdded 30 coins\nBalance: {bal}")

@bot.command(name="check")
@commands.check(check_authorization)
async def check_command(ctx, *, credentials: str = ""):
    """Log in to Outlook and check one or multiple accounts for ChatGPT Plus subscription history"""
    accounts = parse_multiple_credentials(credentials)
    if not accounts:
        await ctx.send("[Warning] Invalid format! Please use: !check email:password (or list multiple separated by spaces/newlines).")
        return

    total = len(accounts)
    status_msg = await ctx.send(f"[Status] Starting subscription check for {total} account(s)...")

    subscribed_list = []
    not_subscribed_list = []
    failed_list = []

    for index, (email, password) in enumerate(accounts, 1):
        await status_msg.edit(content=f"[Status] Processing account {index}/{total}: {email}...")

        async with bot_semaphore:
            with active_checks_lock:
                global active_checks
                active_checks += 1

            local_driver = None
            try:
                status, local_driver = await asyncio.to_thread(check_chatgpt_plus_in_outlook, email, password)
                if status == "Subscribed":
                    subscribed_list.append(email)
                elif status == "Not Subscribed":
                    not_subscribed_list.append(email)
                elif status.startswith("Error:"):
                    failed_list.append((email, status[6:]))
                else:
                    failed_list.append((email, "Unknown Status"))
            except Exception as err:
                print(f"Error checking {email}: {err}")
                failed_list.append((email, str(err).splitlines()[0]))
            finally:
                if local_driver:
                    try:
                        local_driver.quit()
                    except:
                        pass

                with active_checks_lock:
                    active_checks -= 1
                    is_idle = (active_checks == 0)

                gc.collect()
                if is_idle:
                    cleanup_chrome_processes()

    report = []
    report.append("[Report] ChatGPT Plus Verification Summary:")
    report.append("="*45)

    if subscribed_list:
        report.append(f"[Success] Subscribed (Plus active) [{len(subscribed_list)}]:")
        for email in subscribed_list:
            report.append(f"• {email}")

    if not_subscribed_list:
        if len(report) > 2:
            report.append("")
        report.append(f"[Not Subscribed] [{len(not_subscribed_list)}]:")
        for email in not_subscribed_list:
            report.append(f"• {email}")

    if failed_list:
        if len(report) > 2:
            report.append("")
        report.append(f"[Error / Failed] [{len(failed_list)}]:")
        for email, reason in failed_list:
            report.append(f"• {email} (Reason: {reason})")

    report.append("="*45)
    report.append("All checks complete.")

    final_report_text = "\n".join(report)
    if len(final_report_text) > 2000:
        import io
        file_data = io.BytesIO(final_report_text.encode('utf-8'))
        await ctx.send("[Report] Summary Report (Attached due to length limit):", file=discord.File(file_data, "check_report.txt"))
    else:
        await ctx.send(final_report_text)

    try:
        await status_msg.delete()
    except:
        pass

@bot.command(name="otp")
@commands.check(check_authorization)
async def otp_command(ctx, *, credentials: str = ""):
    """Log in to Outlook and retrieve the 6-digit ChatGPT verification code"""
    if not credentials:
        await ctx.send("[Warning] Invalid format! Please use: !otp email:password")
        return

    if ":" not in credentials:
        await ctx.send("[Warning] Invalid format! Please use: !otp email:password")
        return

    email, password = credentials.split(":", 1)
    email = email.strip()
    password = password.strip()

    status_msg = await ctx.send(f"[Status] Logging into {email} to retrieve verification code...")

    async with bot_semaphore:
        with active_checks_lock:
            global active_checks
            active_checks += 1

        local_driver = None
        try:
            otp_code, local_driver = await asyncio.to_thread(fetch_otp_from_outlook, email, password)
        except Exception as e:
            print(f"OTP Checker Error: {e}")
            await status_msg.edit(content="[Error] OTP checker execution failed.")
            return
        finally:
            if local_driver:
                try:
                    local_driver.quit()
                except:
                    pass

            with active_checks_lock:
                active_checks -= 1
                is_idle = (active_checks == 0)

            gc.collect()
            if is_idle:
                cleanup_chrome_processes()

    if otp_code:
        await status_msg.edit(content=f"[Success] OTP Retrieval Successful!\nVerification Code: {otp_code}")
    else:
        await status_msg.edit(content=f"[Failure] Could not find a ChatGPT verification code in the last 2 minutes. Please trigger 'Send code' in your browser and try again.")

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
            print("[Self-Pinger] Ping successful! Keeping app awake.")
        except Exception as e:
            print(f"[Self-Pinger] Ping failed: {e}")
        time.sleep(600)

# --- START BOT ---
if __name__ == "__main__":
    port_env = os.getenv("PORT")
    if port_env:
        port = int(port_env)
        threading.Thread(target=run_http_server, args=(port,), daemon=True).start()
        threading.Thread(target=keep_awake, daemon=True).start()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERROR: DISCORD_TOKEN is missing! Please set it in your .env file.")
    else:
        print("Starting Discord Bot...")
        bot.run(token)