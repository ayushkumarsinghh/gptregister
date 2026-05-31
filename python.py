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

bot_semaphore = asyncio.Semaphore(3)

active_checks = 0
active_checks_lock = threading.Lock()

# --- ACCESS CONTROL SYSTEM ---
OWNER_IDS = [1503647930098122783, 1399261885194309654]
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
        
        email_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@id='i0116'] | //input[@name='loginfmt'] | //input[@type='email']")))
        email_input.clear()
        email_input.send_keys(email)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_input)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@id='idSIButton9'] | //input[@type='submit'] | //button[@type='submit']"))).click()
        
        password_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@id='passwordEntry'] | //input[@id='i0118'] | //input[@name='passwd'] | //input[@type='password']")))
        password_input.clear()
        password_input.send_keys(password)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", password_input)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@data-testid='primaryButton'] | //input[@id='idSIButton9'] | //input[@type='submit'] | //button[@type='submit']"))).click()
        
        time.sleep(2)
        for i in range(7):
            try:
                cancel_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Cancel')] | //input[@id='idCancel'] | //*[@id='idCancel'] | //input[@value='Cancel'] | //*[contains(text(), 'Cancel')]")
                passkey_header = driver.find_elements(By.XPATH, "//*[contains(text(), 'Setting up your passkey') or contains(text(), 'passkey')]")
                if cancel_btns and (cancel_btns[0].is_displayed() or (passkey_header and len(passkey_header) > 0)):
                    cancel_btns[0].click()
                    time.sleep(3)
                    continue
                
                skip_btns = driver.find_elements(By.ID, "iShowSkip")
                if skip_btns and skip_btns[0].is_displayed():
                    skip_btns[0].click()
                    time.sleep(3)
                else:
                    skip_btns_xpath = driver.find_elements(By.XPATH, "//*[contains(@id, 'iShowSkip') or contains(text(), 'Skip for now')]")
                    if skip_btns_xpath and skip_btns_xpath[0].is_displayed():
                        skip_btns_xpath[0].click()
                        time.sleep(3)
                    else:
                        break
            except:
                break
                
        # Try to bypass "Stay signed in?" screen or other intermediate pages
        try:
            stay_signed_no = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@id='idBtn_Back'] | //button[@data-testid='secondaryButton'] | //button[contains(text(), 'No')] | //input[@value='No']"))
            )
            stay_signed_no.click()
            print("Successfully bypassed 'Stay signed in?' screen.")
        except Exception:
            pass
            
        print("Outlook logged in. Scanning for ChatGPT verification code...")
        time.sleep(3)
        
        start_time = time.time()
        extracted_otp = None
        
        while time.time() - start_time < 120:
            try:
                # Force refresh the inbox page to get the absolute latest emails instantly
                driver.get("https://outlook.live.com/mail/0/inbox")
                time.sleep(5)
                
                items = driver.find_elements(By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")
                if items:
                    for item in items[:5]:
                        text = item.text or ""
                        aria_label = item.get_attribute("aria-label") or ""
                        combined_text = (text + " " + aria_label).lower()
                        
                        if "chatgpt" in combined_text or "openai" in combined_text or "verification" in combined_text or "temporary login" in combined_text:
                            # 1. Try extracting 6-digit code directly from preview
                            match = re.search(r'\b\d{6}\b', combined_text)
                            if match:
                                extracted_otp = match.group(0)
                                print(f"Found code directly in email preview: {extracted_otp}")
                                return extracted_otp, driver
                                
                            # 2. Click to open email if not in preview
                            item.click()
                            time.sleep(4)
                            
                            try:
                                elements = driver.find_elements(By.XPATH, "//*[contains(@style, 'Menlo') or contains(@style, 'Monaco') or contains(@style, 'F3F3F3')]")
                                for elem in elements:
                                    val = elem.text.strip()
                                    if len(val) == 6 and val.isdigit():
                                        return val, driver
                            except:
                                pass
                            
                            try:
                                body_text = driver.find_element(By.TAG_NAME, "body").text
                                match = re.search(r'(?:code|continue|verification):\s*(\d{6})', body_text, re.IGNORECASE)
                                if match:
                                    return match.group(1), driver
                                else:
                                    matches = re.findall(r'\b\d{6}\b', body_text)
                                    if matches:
                                        return matches[0], driver
                            except:
                                pass
            except Exception as scan_err:
                print(f"Error during inbox scanning: {scan_err}")
            time.sleep(5)
            
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
        
        email_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@id='i0116'] | //input[@name='loginfmt'] | //input[@type='email']")))
        email_input.clear()
        email_input.send_keys(email)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_input)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@id='idSIButton9'] | //input[@type='submit'] | //button[@type='submit']"))).click()
        
        password_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@id='passwordEntry'] | //input[@id='i0118'] | //input[@name='passwd'] | //input[@type='password']")))
        password_input.clear()
        password_input.send_keys(password)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", password_input)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@data-testid='primaryButton'] | //input[@id='idSIButton9'] | //input[@type='submit'] | //button[@type='submit']"))).click()
        
        time.sleep(2)
        for i in range(7):
            try:
                cancel_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Cancel')] | //input[@id='idCancel'] | //*[@id='idCancel'] | //input[@value='Cancel'] | //*[contains(text(), 'Cancel')]")
                passkey_header = driver.find_elements(By.XPATH, "//*[contains(text(), 'Setting up your passkey') or contains(text(), 'passkey')]")
                if cancel_btns and (cancel_btns[0].is_displayed() or (passkey_header and len(passkey_header) > 0)):
                    cancel_btns[0].click()
                    time.sleep(3)
                    continue
                
                skip_btns = driver.find_elements(By.ID, "iShowSkip")
                if skip_btns and skip_btns[0].is_displayed():
                    skip_btns[0].click()
                    time.sleep(3)
                else:
                    skip_btns_xpath = driver.find_elements(By.XPATH, "//*[contains(@id, 'iShowSkip') or contains(text(), 'Skip for now')]")
                    if skip_btns_xpath and skip_btns_xpath[0].is_displayed():
                        skip_btns_xpath[0].click()
                        time.sleep(3)
                    else:
                        break
            except:
                break
                
        # Try to bypass "Stay signed in?" screen or other intermediate pages
        try:
            stay_signed_no = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@id='idBtn_Back'] | //button[@data-testid='secondaryButton'] | //button[contains(text(), 'No')] | //input[@value='No']"))
            )
            stay_signed_no.click()
            print("Successfully bypassed 'Stay signed in?' screen.")
        except Exception:
            pass
            
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





# --- DISCORD BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🤖 Bot is logged in and ready as: {bot.user}")

def parse_credentials(ctx, user_input):
    if ":" not in user_input:
        return None, None
    email, password = user_input.split(":", 1)
    return email.strip(), password.strip()

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
        raise commands.CheckFailure("❌ **Access Denied!** You do not have permission to run bot commands.")
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
        await ctx.send("❌ **Access Denied!** Only the bot Owner can run this command.")
        return
        
    target_id = extract_userid(user_input)
    if not target_id:
        await ctx.send("⚠️ **Invalid format!** Please use: `!adduser @user` or `!adduser <discorduserid>`")
        return
        
    allowed_list = load_allowed_users()
    if target_id in allowed_list:
        await ctx.send(f"ℹ️ User <@{target_id}> is already in the allowed list.")
        return
        
    allowed_list.append(target_id)
    save_allowed_users(allowed_list)
    await ctx.send(f"✅ **[Access Granted]** User <@{target_id}> (ID: `{target_id}`) has been successfully authorized to run bot commands!")

@bot.command(name="removeuser")
async def removeuser_command(ctx, *, user_input: str = ""):
    """Remove a Discord User ID from the allowed users list (Owner Only)"""
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("❌ **Access Denied!** Only the bot Owner can run this command.")
        return
        
    target_id = extract_userid(user_input)
    if not target_id:
        await ctx.send("⚠️ **Invalid format!** Please use: `!removeuser @user` or `!removeuser <discorduserid>`")
        return
        
    allowed_list = load_allowed_users()
    if target_id not in allowed_list:
        await ctx.send(f"⚠️ User <@{target_id}> is not in the allowed list.")
        return
        
    allowed_list.remove(target_id)
    save_allowed_users(allowed_list)
    await ctx.send(f"❌ **[Access Revoked]** User <@{target_id}> (ID: `{target_id}`) has been removed from authorized access.")

@bot.command(name="listusers")
async def listusers_command(ctx):
    """List all authorized Discord User IDs (Owner Only)"""
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("❌ **Access Denied!** Only the bot Owner can run this command.")
        return
        
    allowed_list = load_allowed_users()
    report = []
    report.append("📋 **Authorized Discord Users List:**")
    report.append("="*40)
    
    owners_list = [f"<@{o_id}> (ID: `{o_id}`)" for o_id in OWNER_IDS]
    report.append(f"👑 **Owners:** {', '.join(owners_list)}")
    
    if allowed_list:
        report.append(f"👤 **Allowed Users [{len(allowed_list)}]:**")
        for u_id in allowed_list:
            report.append(f"• <@{u_id}> (ID: `{u_id}`)")
    else:
        report.append("👤 *No extra users have been added yet.*")
        
    report.append("="*40)
    await ctx.send("\n".join(report))


# --- PRIMARY WORKER BOT COMMANDS (PROTECTED) ---

@bot.command(name="otp")
@commands.check(check_authorization)
async def otp_command(ctx, *, credentials: str = ""):
    """Log in to Outlook and automatically fetch the latest 6-digit ChatGPT OTP / verification code"""
    email, password = parse_credentials(ctx, credentials)
    if not email or not password:
        await ctx.send("⚠️ **Invalid format!** Please use: `!otp email:password`")
        return
        
    await ctx.send(f"⏳ **[Outlook OTP]** Logging into `{email}` to retrieve your 6-digit verification code...")
    
    async with bot_semaphore:
        # Increment active checking counter
        with active_checks_lock:
            global active_checks
            active_checks += 1

        local_driver = None
        try:
            otp_code, local_driver = await asyncio.to_thread(fetch_otp_from_outlook, email, password)
            if otp_code:
                await ctx.send(f"🎉 **[OTP Retrieval Successful]**")
                await ctx.send(f"🔑 **Verification Code (Tap to copy):**")
                await ctx.send(f"`{otp_code}`")
            else:
                await ctx.send(f"❌ **[OTP Retrieval Failed]** Could not find a ChatGPT verification code in the last 2 minutes. Please trigger 'Send code' in your browser and try again.")
        except Exception as err:
            await ctx.send(f"⚠️ **[OTP Error]** An unexpected exception occurred: `{err}`")
        finally:
            if local_driver:
                try:
                    local_driver.quit()
                except:
                    pass

            # Decrement active checking counter and read idle state
            with active_checks_lock:
                active_checks -= 1
                is_idle = (active_checks == 0)

            # Perform basic heap garbage collection
            gc.collect()

            # Run aggressive process sweeping only when all checking threads are idle
            if is_idle:
                cleanup_chrome_processes()

@bot.command(name="check")
@commands.check(check_authorization)
async def check_command(ctx, *, credentials: str = ""):
    """Log in to Outlook and check one or multiple accounts for ChatGPT Plus subscription history"""
    accounts = parse_multiple_credentials(credentials)
    if not accounts:
        await ctx.send("⚠️ **Invalid format!** Please use: `!check email:password` (or list multiple separated by spaces/newlines).")
        return
        
    total = len(accounts)
    status_msg = await ctx.send(f"⏳ **[Outlook Check]** Starting subscription check for **{total}** account(s)...")
    
    subscribed_list = []
    not_subscribed_list = []
    failed_list = []
    
    for index, (email, password) in enumerate(accounts, 1):
        await status_msg.edit(content=f"⏳ **[Outlook Check]** Processing account **{index}/{total}**: `{email}`...")
        
        async with bot_semaphore:
            # Increment active checking counter
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
                
                # Decrement active checking counter and read idle state
                with active_checks_lock:
                    active_checks -= 1
                    is_idle = (active_checks == 0)

                # Perform basic heap garbage collection
                gc.collect()

                # Run aggressive process sweeping only when all checking threads are idle
                if is_idle:
                    cleanup_chrome_processes()
                        
    report = []
    report.append("📋 **ChatGPT Plus Verification Summary Report:**")
    report.append("="*45)
    
    if subscribed_list:
        report.append(f"🎉 **Subscribed (Plus active) [{len(subscribed_list)}]:**")
        for email in subscribed_list:
            report.append(f"• `{email}`")
            
    if not_subscribed_list:
        if len(report) > 2:
            report.append("")
        report.append(f"❌ **Not Subscribed [{len(not_subscribed_list)}]:**")
        for email in not_subscribed_list:
            report.append(f"• `{email}`")
            
    if failed_list:
        if len(report) > 2:
            report.append("")
        report.append(f"⚠️ **Check Failed / Errors [{len(failed_list)}]:**")
        for email, reason in failed_list:
            report.append(f"• `{email}` (Reason: *{reason}*)")
            
    report.append("="*45)
    report.append("✓ *All checks complete.*")
    
    final_report_text = "\n".join(report)
    if len(final_report_text) > 2000:
        import io
        file_data = io.BytesIO(final_report_text.encode('utf-8'))
        await ctx.send("📋 **Summary Report (Attached due to length limit):**", file=discord.File(file_data, "check_report.txt"))
    else:
        await ctx.send(final_report_text)
        
    try:
        await status_msg.delete()
    except:
        pass


        

# --- START BOT ---
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERROR: DISCORD_TOKEN is missing! Please set it in your .env file.")
    else:
        print("Starting Discord Bot...")
        bot.run(token)