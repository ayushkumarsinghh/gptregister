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
                key, val = line.strip().split("=", 1)
                os.environ[key] = val

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
        
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        
        is_cloud = os.getenv("DOCKER_ENV") == "true" or os.name != 'nt'
        
        if is_cloud:
            print("Cloud server detected. Initializing Headless Chrome options...")
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            driver = uc.Chrome(options=options)
        else:
            print("Local Windows machine detected. Starting Chrome in standard GUI mode...")
            driver = uc.Chrome(options=options, version_main=147)
            
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
                try:
                    driver.quit()
                except:
                    pass
                return False, None
                
            time.sleep(5)

            print("Monitoring for OpenAI verification codes...")
            
            start_time = time.time()
            while time.time() - start_time < 300:
                try:
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
                        except Exception:
                            pass
                        
                        return True, driver
                except Exception as e:
                    print("Error during code checking cycle:", e)
                
                time.sleep(2)
            
            print("Search timed out.")
            try:
                driver.quit()
            except:
                pass
            return False, None
            
        except Exception as e:
            print("Flow failed:", e)
            try:
                driver.quit()
            except:
                pass
            return False, None

def save_session_to_file(pre_text):
    try:
        with open(SESSION_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(pre_text)
        print(f"Saved to: {os.path.abspath(SESSION_FILE_PATH)}")
    except Exception as e:
        print(f"Failed to save: {e}")

def fill_profile_form(driver):
    wait = WebDriverWait(driver, 30)
    
    print("Waiting for profile registration form to load...")
    try:
        wait.until(EC.presence_of_element_located((By.NAME, "name")))
        print("Profile form detected successfully.")
    except Exception as wait_err:
        print("Timed out waiting for profile form, proceeding anyway:", wait_err)
        
    time.sleep(2)
    
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
    try:
        name_input = driver.find_element(By.ID, "_r_h_-name")
        if type_slowly(name_input, random_full):
            print(f"Filled name field: {random_full}")
            name_filled = True
    except Exception:
        pass
    
    if not name_filled:
        try:
            name_input = driver.find_element(By.NAME, "name")
            if type_slowly(name_input, random_full):
                print(f"Filled name field: {random_full}")
                name_filled = True
        except Exception:
            pass

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
        print(f"✓ Age successfully filled: {random_age}")

    print("Looking for submit button...")
    try:
        finish_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Finish') or contains(text(), 'Agree') or contains(text(), 'Continue') or contains(text(), 'Finish creating account')]"))
        )
        finish_btn.click()
        print("Clicked finish button.")
    except Exception as e:
        print(f"Could not click submit: {e}")

    print("Waiting 4 seconds for profile creation...")
    time.sleep(4)
    
    print("Opening ChatGPT session API...")
    driver.switch_to.new_window('tab')
    driver.get(CHATGPT_SESSION_URL)
    time.sleep(3)
    
    try:
        pre_element = wait.until(EC.presence_of_element_located((By.TAG_NAME, "pre")))
        pre_text = pre_element.text
        print("="*50)
        print("Session API Response:")
        print("="*50)
        print(pre_text)
        print("="*50)
        save_session_to_file(pre_text)
        return pre_text
    except Exception as e:
        print(f"Error: {e}")
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

@bot.command(name="check")
async def check_command(ctx, *, credentials: str = ""):
    """Check Outlook + ChatGPT login and verify plan type"""
    email, password = parse_credentials(ctx, credentials)
    if not email or not password:
        await ctx.send("⚠️ **Invalid format!** Please use: `!check email:password`")
        return
        
    await ctx.send(f"⏳ **[Check]** Starting verification & plan check for `{email}`...\n*(Running concurrently. Max limit: 3 Chrome instances)*")
    
    async with bot_semaphore:
        local_driver = None
        try:
            # Run Selenium in a background thread
            success, local_driver = await asyncio.to_thread(run_flow, email, password)
            if success and local_driver:
                # Fetch plan type directly from session API response
                session_response = await asyncio.to_thread(fetch_session_only, local_driver)
                
                if session_response:
                    try:
                        session_data = json.loads(session_response)
                        plan_type = session_data.get("account", {}).get("planType", "free").lower()
                        
                        if plan_type == "plus" or plan_type == "premium" or plan_type == "durango":
                            await ctx.send(f"✅ **[Check Success]** `{email}` is fully verified!\n📝 **Plan Type:** `PLUS` 🌟 (Plan Exists!)")
                        else:
                            await ctx.send(f"❌ **[Check Result]** `{email}` verified, but it is a **FREE** account (No Plan).")
                    except Exception as parse_err:
                        print(f"Error parsing check session: {parse_err}")
                        await ctx.send(f"✅ **[Check Success]** `{email}` verified, but failed to parse plan details.")
                else:
                    await ctx.send(f"✅ **[Check Success]** `{email}` verified, but session details were empty.")
            else:
                await ctx.send(f"❌ **[Check Failed]** Flow failed for `{email}` (login/error).")
        except Exception as err:
            await ctx.send(f"⚠️ **[Check Error]** An unexpected exception occurred: `{err}`")
        finally:
            if local_driver:
                try:
                    local_driver.quit()
                except:
                    pass

@bot.command(name="session")
async def session_command(ctx, *, credentials: str = ""):
    """Run full flow (login, verification, onboarding) and retrieve the session access token"""
    email, password = parse_credentials(ctx, credentials)
    if not email or not password:
        await ctx.send("⚠️ **Invalid format!** Please use: `!session email:password`")
        return
        
    await ctx.send(f"⏳ **[Session]** Starting registration + session retrieval for `{email}`...\n*(Running concurrently. Max limit: 3 Chrome instances)*")
    
    async with bot_semaphore:
        local_driver = None
        try:
            success, local_driver = await asyncio.to_thread(run_flow, email, password)
            if success and local_driver:
                await ctx.send("✏️ Outlook verification complete. Filling profile registration details (name/age)...")
                session_response = await asyncio.to_thread(fill_profile_form, local_driver)
                
                if session_response:
                    await ctx.send(f"🎉 **[Session Retrieval Successful]** Profile onboarding complete!")
                    
                    try:
                        session_data = json.loads(session_response)
                        compact_json = json.dumps(session_data, separators=(',', ':'))
                        
                        # Direct Copy-friendly single markdown format block
                        msg = f"📋 **Full ChatGPT Session JSON:**\n```json\n{compact_json}\n```"
                        
                        if len(msg) > 2000:
                            # Send raw text directly inside a code block safely
                            await ctx.send(f"📋 **Full ChatGPT Session JSON (Unbroken):**")
                            # If for any reason the compact JSON reaches the upper limit, send it in clean 1900-char text boxes
                            if len(compact_json) <= 1980:
                                await ctx.send(f"```json\n{compact_json}\n```")
                            else:
                                await ctx.send(f"```json\n{compact_json[:1980]}\n```")
                        else:
                            await ctx.send(msg)
                    except Exception as json_err:
                        print(f"Error parsing session response: {json_err}")
                        if len(session_response) <= 1980:
                            await ctx.send(f"```json\n{session_response}\n```")
                        else:
                            await ctx.send(f"```json\n{session_response[:1980]}\n```")
                else:
                    await ctx.send(f"⚠️ Registration completed, but failed to fetch session details from `{CHATGPT_SESSION_URL}`.")
            else:
                await ctx.send(f"❌ **[Session Failed]** Flow failed during Outlook/ChatGPT authentication for `{email}`.")
        except Exception as err:
            await ctx.send(f"⚠️ **[Session Error]** An unexpected exception occurred: `{err}`")
        finally:
            if local_driver:
                try:
                    local_driver.quit()
                except:
                    pass

# --- RUN BOT ---
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERROR: DISCORD_TOKEN is missing! Please set it in your .env file.")
    else:
        print("Starting Discord Bot...")
        bot.run(token)