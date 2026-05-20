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
import discord
from discord.ext import commands
import asyncio
import traceback

# --- CONFIG ---
URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=9199bf20-a13f-4107-85dc-02114787ef48&scope=https%3A%2F%2Foutlook.office.com%2F.default%20openid%20profile%20offline_access&redirect_uri=https%3A%2F%2Foutlook.live.com%2Fmail%2F&client-request-id=85af84fb-4838-c204-f618-76e540231109&response_mode=fragment&client_info=1&prompt=select_account&nonce=019e35f5-4ebc-7f28-8e36-611bb37f46ef&state=eyJpZCI6IjAxOWUzNWY1LTRlYmItNzdmZS04MzkwLTVlMmMzZTFhN2FiMiIsIm1ldGEiOnsiaW50ZXJhY3Rpb25UeXBlIjoicmVkaXJlY3QifX0%3D%7CaHR0cHM6Ly9vdXRsb29rLmxpdmUuY29tL21haWwvP2N1bHR1cmU9ZW4tdXMmY291bnRyeT11Uw&claims=%7B%22access_token%22%3A%7B%22xms_cc%22%3A%7B%22values%22%3A%5B%22CP1%22%5D%7D%7D%7D&x-client-SKU=msal.js.browser&x-client-VER=4.28.2&response_type=code&code_challenge=Y-gIvtWec47bQ-tJO49QiNIoRYFseu5HdBprFFN3Af0&code_challenge_method=S256&cobrandid=ab0455a0-8d03-46b9-b18b-df2f57b9e44c&fl=dob,flname,wld&sso_reload=true"

bot_semaphore = asyncio.Semaphore(3)

# --- ACCESS CONTROL SYSTEM ---
OWNER_ID = 1074981715971428432
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
    if user_id == OWNER_ID:
        return True
    allowed = load_allowed_users()
    return user_id in allowed

# --- HEADLESS CHROMEDRIVER OPTIONS FACTORY ---
def get_chrome_options():
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    is_cloud = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
    if is_cloud:
        options.add_argument("--headless=new")
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
    return options

# --- SELENIUM WORKERS ---

def fetch_otp_from_outlook(email, password):
    options = get_chrome_options()
    is_cloud = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
    if is_cloud:
        driver = uc.Chrome(options=options)
    else:
        driver = uc.Chrome(options=options, version_main=147)
        
    wait = WebDriverWait(driver, 35)
    
    try:
        driver.get(URL)
        print("Navigated to Outlook login page.")
        
        email_input = wait.until(EC.element_to_be_clickable((By.ID, "i0116")))
        email_input.clear()
        email_input.send_keys(email)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_input)
        wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9"))).click()
        
        password_input = wait.until(EC.element_to_be_clickable((By.ID, "passwordEntry")))
        password_input.clear()
        password_input.send_keys(password)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", password_input)
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='primaryButton']"))).click()
        
        time.sleep(2)
        for i in range(5):
            try:
                cancel_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Cancel')] | //input[@id='idCancel'] | //*[@id='idCancel']")
                if cancel_btns:
                    cancel_btns[0].click()
                    time.sleep(2)
                    continue
                skip_btns = driver.find_elements(By.ID, "iShowSkip")
                if skip_btns and skip_btns[0].is_displayed():
                    skip_btns[0].click()
                    time.sleep(2)
                else:
                    break
            except:
                break
                
        try:
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='secondaryButton']"))).click()
        except:
            pass
            
        print("Outlook logged in. Scanning for ChatGPT verification code...")
        time.sleep(3)
        
        start_time = time.time()
        extracted_otp = None
        
        while time.time() - start_time < 120:
            try:
                search_input = wait.until(EC.element_to_be_clickable((By.ID, "topSearchInput")))
                search_input.click()
                search_input.clear()
                search_input.send_keys("chatgpt code")
                search_input.send_keys("\n")
                time.sleep(3)
                
                items = driver.find_elements(By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")
                if items:
                    for item in items[:3]:
                        text = item.text or ""
                        aria_label = item.get_attribute("aria-label") or ""
                        combined_text = (text + " " + aria_label).lower()
                        
                        if "chatgpt" in combined_text or "openai" in combined_text or "verification" in combined_text:
                            match = re.search(r'\b\d{6}\b', combined_text)
                            if match:
                                extracted_otp = match.group(0)
                                return extracted_otp, driver
                                
                            item.click()
                            time.sleep(3)
                            
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
            except:
                pass
            time.sleep(5)
            
        return None, driver
    except Exception as e:
        print(f"OTP extraction failed: {e}")
        return None, driver


def check_chatgpt_plus_in_outlook(email, password):
    options = get_chrome_options()
    is_cloud = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
    if is_cloud:
        driver = uc.Chrome(options=options)
    else:
        driver = uc.Chrome(options=options, version_main=147)
        
    wait = WebDriverWait(driver, 35)
    
    try:
        driver.get(URL)
        
        email_input = wait.until(EC.element_to_be_clickable((By.ID, "i0116")))
        email_input.clear()
        email_input.send_keys(email)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_input)
        wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9"))).click()
        
        password_input = wait.until(EC.element_to_be_clickable((By.ID, "passwordEntry")))
        password_input.clear()
        password_input.send_keys(password)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", password_input)
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='primaryButton']"))).click()
        
        time.sleep(2)
        for i in range(5):
            try:
                cancel_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Cancel')] | //input[@id='idCancel'] | //*[@id='idCancel']")
                if cancel_btns:
                    cancel_btns[0].click()
                    time.sleep(2)
                    continue
                skip_btns = driver.find_elements(By.ID, "iShowSkip")
                if skip_btns and skip_btns[0].is_displayed():
                    skip_btns[0].click()
                    time.sleep(2)
                else:
                    break
            except:
                break
                
        try:
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='secondaryButton']"))).click()
        except:
            pass
            
        print("Outlook logged in. Searching for subscription / invoice keywords...")
        time.sleep(3)
        
        search_input = wait.until(EC.element_to_be_clickable((By.ID, "topSearchInput")))
        search_input.click()
        search_input.clear()
        search_input.send_keys("chatgpt plus")
        search_input.send_keys("\n")
        time.sleep(4)
        
        items = driver.find_elements(By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")
        if items:
            for item in items[:5]:
                text = (item.text or "").lower()
                aria_label = (item.get_attribute("aria-label") or "").lower()
                combined_text = text + " " + aria_label
                if "chatgpt plus" in combined_text or "subscription" in combined_text or "receipt" in combined_text or "invoice" in combined_text or "payment" in combined_text:
                    return "Subscribed", driver
                    
        # Secondary check
        search_input = wait.until(EC.element_to_be_clickable((By.ID, "topSearchInput")))
        search_input.click()
        search_input.clear()
        search_input.send_keys("openai subscription")
        search_input.send_keys("\n")
        time.sleep(4)
        
        items = driver.find_elements(By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")
        if items:
            for item in items[:5]:
                text = (item.text or "").lower()
                aria_label = (item.get_attribute("aria-label") or "").lower()
                combined_text = text + " " + aria_label
                if "openai" in combined_text and ("subscription" in combined_text or "payment" in combined_text or "receipt" in combined_text or "invoice" in combined_text or "plus" in combined_text):
                    return "Subscribed", driver
                    
        return "Not Subscribed", driver
    except Exception as e:
        print(f"Check failed: {e}")
        return "Error", driver


def run_full_access_token_flow(email, password):
    options = get_chrome_options()
    is_cloud = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
    if is_cloud:
        driver = uc.Chrome(options=options)
    else:
        driver = uc.Chrome(options=options, version_main=147)
        
    wait = WebDriverWait(driver, 35)
    
    try:
        # 1. Log into Outlook
        driver.get(URL)
        original_window = driver.current_window_handle
        
        email_input = wait.until(EC.element_to_be_clickable((By.ID, "i0116")))
        email_input.clear()
        email_input.send_keys(email)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_input)
        wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9"))).click()
        
        password_input = wait.until(EC.element_to_be_clickable((By.ID, "passwordEntry")))
        password_input.clear()
        password_input.send_keys(password)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", password_input)
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='primaryButton']"))).click()
        
        time.sleep(2)
        for i in range(5):
            try:
                cancel_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Cancel')] | //input[@id='idCancel'] | //*[@id='idCancel']")
                if cancel_btns:
                    cancel_btns[0].click()
                    time.sleep(2)
                    continue
                skip_btns = driver.find_elements(By.ID, "iShowSkip")
                if skip_btns and skip_btns[0].is_displayed():
                    skip_btns[0].click()
                    time.sleep(2)
                else:
                    break
            except:
                break
                
        try:
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='secondaryButton']"))).click()
        except:
            pass
            
        # 2. Open ChatGPT and start login
        driver.switch_to.new_window('tab')
        chatgpt_window = driver.current_window_handle
        driver.get("https://chatgpt.com/")
        time.sleep(4)
        
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='login-button']"))).click()
        
        chatgpt_email = wait.until(EC.element_to_be_clickable((By.ID, "email")))
        chatgpt_email.clear()
        chatgpt_email.send_keys(email)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", chatgpt_email)
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()
        time.sleep(4)
        
        # 3. Switch back to Outlook and grab OTP
        driver.switch_to.window(original_window)
        extracted_otp = None
        start_time = time.time()
        
        while time.time() - start_time < 90:
            try:
                search_input = wait.until(EC.element_to_be_clickable((By.ID, "topSearchInput")))
                search_input.click()
                search_input.clear()
                search_input.send_keys("chatgpt code")
                search_input.send_keys("\n")
                time.sleep(3)
                
                items = driver.find_elements(By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")
                if items:
                    for item in items[:2]:
                        text = (item.text or "").lower()
                        aria_label = (item.get_attribute("aria-label") or "").lower()
                        combined_text = text + " " + aria_label
                        if "chatgpt" in combined_text or "openai" in combined_text:
                            match = re.search(r'\b\d{6}\b', combined_text)
                            if match:
                                extracted_otp = match.group(0)
                                break
                    if extracted_otp:
                        break
            except:
                pass
            time.sleep(5)
            
        if not extracted_otp:
            return None, driver
            
        # 4. Switch back to ChatGPT and enter OTP
        driver.switch_to.window(chatgpt_window)
        for index, digit in enumerate(extracted_otp):
            input_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, f"input[data-index='{index}']")))
            input_field.clear()
            input_field.send_keys(digit)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", input_field)
        time.sleep(5)
        
        # 5. Onboarding name and age filling
        try:
            first_name_input = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.ID, "first_name")))
            first_name_input.clear()
            first_name_input.send_keys("Alex")
            
            last_name_input = driver.find_element(By.ID, "last_name")
            last_name_input.clear()
            last_name_input.send_keys("Smith")
            
            for btn_sel in ["button[type='submit']", "form button", "button"]:
                try:
                    driver.find_element(By.CSS_SELECTOR, btn_sel).click()
                    break
                except:
                    pass
            time.sleep(4)
        except:
            pass
            
        try:
            month_input = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.ID, "birthdate-month")))
            month_input.clear()
            month_input.send_keys("05")
            
            day_input = driver.find_element(By.ID, "birthdate-day")
            day_input.clear()
            day_input.send_keys("15")
            
            year_input = driver.find_element(By.ID, "birthdate-year")
            year_input.clear()
            year_input.send_keys("1998")
            
            for btn_sel in ["button[type='submit']", "form button", "button"]:
                try:
                    driver.find_element(By.CSS_SELECTOR, btn_sel).click()
                    break
                except:
                    pass
            time.sleep(6)
        except:
            pass
            
        # 6. Open session JSON
        driver.switch_to.new_window('tab')
        driver.get("https://chatgpt.com/api/auth/session")
        time.sleep(4)
        
        pre_element = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "pre")))
        session_text = pre_element.text
        return session_text, driver
    except Exception as e:
        print(f"Access flow failed: {e}")
        return None, driver


# --- DISCORD BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
def on_ready():
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
    if ctx.author.id != OWNER_ID:
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
    if ctx.author.id != OWNER_ID:
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
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ **Access Denied!** Only the bot Owner can run this command.")
        return
        
    allowed_list = load_allowed_users()
    report = []
    report.append("📋 **Authorized Discord Users List:**")
    report.append("="*40)
    report.append(f"👑 **Owner:** <@{OWNER_ID}> (ID: `{OWNER_ID}`)")
    
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
            local_driver = None
            try:
                status, local_driver = await asyncio.to_thread(check_chatgpt_plus_in_outlook, email, password)
                if status == "Subscribed":
                    subscribed_list.append(email)
                elif status == "Not Subscribed":
                    not_subscribed_list.append(email)
                else:
                    failed_list.append(email)
            except Exception as err:
                print(f"Error checking {email}: {err}")
                failed_list.append(email)
            finally:
                if local_driver:
                    try:
                        local_driver.quit()
                    except:
                        pass
                        
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
        for email in failed_list:
            report.append(f"• `{email}`")
            
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

@bot.command(name="access")
@commands.check(check_authorization)
async def access_command(ctx, *, credentials: str = ""):
    """Log in to Outlook, authenticate ChatGPT, and retrieve the full access token block"""
    email, password = parse_credentials(ctx, credentials)
    if not email or not password:
        await ctx.send("⚠️ **Invalid format!** Please use: `!access email:password`")
        return
        
    await ctx.send(f"⏳ **[Outlook Access]** Logging into `{email}` and authenticating ChatGPT session token...")
    
    async with bot_semaphore:
        local_driver = None
        try:
            session_json, local_driver = await asyncio.to_thread(run_full_access_token_flow, email, password)
            if session_json:
                try:
                    session_data = json.loads(session_json)
                    access_token = session_data.get("accessToken", "")
                except Exception:
                    access_token = ""
                    
                await ctx.send(f"🎉 **[Access Token Retrieval Successful]**")
                if access_token:
                    await ctx.send("📋 **Access Token (Tap to copy):**")
                    await ctx.send(f"`{access_token}`")
                    
                import io
                file_data = io.BytesIO(session_json.encode('utf-8'))
                await ctx.send("📄 **Full Session Details:**", file=discord.File(file_data, "session.json"))
            else:
                await ctx.send(f"❌ **[Access Token Failed]** Could not retrieve session data. Please ensure credentials are correct and try again.")
        except Exception as err:
            await ctx.send(f"⚠️ **[Access Token Error]** An unexpected exception occurred: `{err}`")
        finally:
            if local_driver:
                try:
                    local_driver.quit()
                except:
                    pass


# --- RAILWAY HEALTH CHECK PORT LISTENER ---
def start_health_check_server():
    import http.server
    import socketserver
    import threading
    
    port = int(os.getenv("PORT", 8080))
    class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        def log_message(self, format, *args):
            pass # Suppress server noise
            
    try:
        server = socketserver.TCPServer(("", port), HealthCheckHandler)
        print(f"Railway Health Check server started on port {port}")
        threading.Thread(target=server.serve_forever, daemon=True).start()
    except Exception as e:
        print(f"Failed to start Railway Health Check server: {e}")

# --- START BOT ---
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERROR: DISCORD_TOKEN is missing! Please set it in your .env file.")
    else:
        start_health_check_server()
        print("Starting Discord Bot...")
        bot.run(token)