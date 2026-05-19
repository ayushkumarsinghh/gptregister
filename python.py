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

def fetch_otp_from_outlook(email, password):
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
        
    wait = WebDriverWait(driver, 35)
    
    try:
        # Navigate to Outlook login page
        driver.get(URL)
        print("Navigated to Outlook URL successfully.")
        
        # 1. Enter email
        email_input = wait.until(EC.element_to_be_clickable((By.ID, "i0116")))
        email_input.clear()
        email_input.send_keys(email)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_input)
        
        next_btn = wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9")))
        next_btn.click()
        print("Email submitted.")
        
        # 2. Enter password
        password_input = wait.until(EC.element_to_be_clickable((By.ID, "passwordEntry")))
        password_input.clear()
        password_input.send_keys(password)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", password_input)
        
        submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='primaryButton']")))
        submit_btn.click()
        print("Password submitted.")
        
        # 3. Handle security / passkey prompts
        time.sleep(2)
        for i in range(7):
            try:
                cancel_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Cancel')] | //input[@id='idCancel'] | //*[@id='idCancel'] | //input[@value='Cancel'] | //*[contains(text(), 'Cancel')]")
                passkey_header = driver.find_elements(By.XPATH, "//*[contains(text(), 'Setting up your passkey') or contains(text(), 'passkey')]")
                
                if cancel_btns and (cancel_btns[0].is_displayed() or (passkey_header and len(passkey_header) > 0)):
                    cancel_btns[0].click()
                    print(f"Clicked Microsoft Passkey 'Cancel' (Attempt {i+1})!")
                    time.sleep(3)
                    continue
                
                skip_btns = driver.find_elements(By.ID, "iShowSkip")
                if skip_btns and skip_btns[0].is_displayed():
                    skip_btns[0].click()
                    print("Clicked 'Skip for now'.")
                    time.sleep(2)
                else:
                    skip_btns_xpath = driver.find_elements(By.XPATH, "//*[contains(@id, 'iShowSkip') or contains(text(), 'Skip for now')]")
                    if skip_btns_xpath and skip_btns_xpath[0].is_displayed():
                        skip_btns_xpath[0].click()
                        print("Clicked 'Skip for now' via XPath.")
                        time.sleep(2)
                    else:
                        break
            except Exception as e_skip:
                print(f"Skip/Cancel iteration {i+1} handled exception: {e_skip}")
                break
                
        # 4. Handle "Stay signed in"
        print("Checking stay signed in...")
        try:
            no_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='secondaryButton']")))
            no_btn.click()
            print("Clicked 'No' on 'Stay signed in' prompt.")
        except Exception:
            try:
                no_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'No') or contains(text(), 'no')]")))
                no_btn.click()
                print("Clicked 'No' on 'Stay signed in' via text match.")
            except Exception as stay_signed_err:
                print("Stay signed in prompt did not appear or failed:", stay_signed_err)
                
        # 5. Search inbox for ChatGPT code
        print("Inbox loaded successfully. Scanning for ChatGPT verification emails...")
        time.sleep(3)
        
        # We try to search and scan for up to 2 minutes (waiting for the email to arrive)
        start_search_time = time.time()
        extracted_otp = None
        
        while time.time() - start_search_time < 120:
            try:
                # Type query in Outlook search
                search_input = wait.until(EC.element_to_be_clickable((By.ID, "topSearchInput")))
                search_input.click()
                search_input.clear()
                search_input.send_keys("chatgpt code")
                search_input.send_keys("\n")
                print("Submitted search query.")
                time.sleep(3)
                
                # Check matching email items
                items = driver.find_elements(By.CSS_SELECTOR, "div[data-focusable-row='true'][role='option']")
                if items:
                    print(f"Found {len(items)} matching emails in search results.")
                    
                    # Scan the top 3 matching emails
                    for item in items[:3]:
                        text = item.text or ""
                        aria_label = item.get_attribute("aria-label") or ""
                        combined_text = (text + " " + aria_label).lower()
                        
                        if "chatgpt" in combined_text or "openai" in combined_text or "verification" in combined_text:
                            # Level 1: Match 6-digit code directly from email preview text
                            match = re.search(r'\b\d{6}\b', combined_text)
                            if match:
                                extracted_otp = match.group(0)
                                print(f"✓ Found OTP in email list preview: {extracted_otp}")
                                return extracted_otp, driver
                                
                            # Level 2: Click the email to read full body
                            item.click()
                            print("Clicked email to load full content...")
                            time.sleep(3)
                            
                            # Read OTP inside standard Menlo/Monaco code block
                            try:
                                elements = driver.find_elements(By.XPATH, "//*[contains(@style, 'Menlo') or contains(@style, 'Monaco') or contains(@style, 'F3F3F3')]")
                                for elem in elements:
                                    text_val = elem.text.strip()
                                    if len(text_val) == 6 and text_val.isdigit():
                                        extracted_otp = text_val
                                        print(f"✓ Extracted OTP from open email block: {extracted_otp}")
                                        return extracted_otp, driver
                            except Exception:
                                pass
                                
                            # Level 3: Regex match search inside full body text
                            try:
                                page_text = driver.find_element(By.TAG_NAME, "body").text
                                match = re.search(r'(?:code|continue|verification):\s*(\d{6})', page_text, re.IGNORECASE)
                                if match:
                                    extracted_otp = match.group(1)
                                    print(f"✓ Extracted OTP via body regex: {extracted_otp}")
                                    return extracted_otp, driver
                                else:
                                    matches = re.findall(r'\b\d{6}\b', page_text)
                                    if matches:
                                        extracted_otp = matches[0]
                                        print(f"✓ Extracted first 6-digit match in body: {extracted_otp}")
                                        return extracted_otp, driver
                            except Exception:
                                pass
            except Exception as loop_err:
                print(f"Error in search loop: {loop_err}")
                
            time.sleep(5)
            
        print("[-] Verification email not found within 120 seconds.")
        return None, driver
        
    except Exception as e:
        print(f"Execution failed: {e}")
        return None, driver


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

# Primary Command: !otp
@bot.command(name="otp")
async def otp_command(ctx, *, credentials: str = ""):
    """Log in to Outlook and automatically fetch the latest 6-digit ChatGPT OTP / verification code"""
    email, password = parse_credentials(ctx, credentials)
    if not email or not password:
        await ctx.send("⚠️ **Invalid format!** Please use: `!otp email:password`")
        return
        
    await ctx.send(f"⏳ **[Outlook OTP]** Logging into `{email}` to retrieve your 6-digit verification code...\n*(Running concurrently. Max limit: 3 Chrome instances)*")
    
    async with bot_semaphore:
        local_driver = None
        try:
            # Run Selenium in a background thread
            otp_code, local_driver = await asyncio.to_thread(fetch_otp_from_outlook, email, password)
            
            if otp_code:
                # Output OTP code in direct copy block and clean text
                await ctx.send(f"🎉 **[OTP Retrieval Successful]**")
                await ctx.send(f"🔑 **Verification Code:**\n```\n{otp_code}\n```")
            else:
                await ctx.send(f"❌ **[OTP Retrieval Failed]** Could not find a ChatGPT verification code in the last 2 minutes. Please trigger 'Send code' in your browser and try again.")
        except Exception as err:
            await ctx.send(f"⚠️ **[OTP Error]** An unexpected exception occurred: `{err}`")
        finally:
            if local_driver:
                try:
                    local_driver.quit()
                    print("Chrome driver terminated successfully.")
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