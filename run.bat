@echo off
title Outlook OTP Bot 24/7 Runner
:loop
echo [%date% %time%] Starting Outlook OTP Discord Bot...
python py3.py
echo [%date% %time%] Bot crashed or closed. Restarting in 5 seconds...
timeout /t 5 >nul
goto loop
