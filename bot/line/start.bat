@echo off
chcp 65001 >nul
title THSR LINE Bot

:: Kill leftover ngrok process
taskkill /F /IM ngrok.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:: Start Flask + ngrok (use project root .venv)
cd /d "%~dp0"
..\..\.venv\Scripts\python.exe app.py
pause
