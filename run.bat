@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8

echo Starting THSR auto booking...

REM ==========================================
REM Booking Parameters
REM ==========================================

REM Skip history selection: 1=skip
set SKIP_HISTORY=1

REM Start station: 1=Nangang 2=Taipei 3=Banqiao 4=Taoyuan 5=Hsinchu 6=Miaoli 7=Taichung 8=Changhua 9=Yunlin 10=Chiayi 11=Tainan 12=Zuoying
set START_STATION=4

REM Destination station
set DEST_STATION=11

REM Outbound date: YYYY/MM/DD
set OUTBOUND_DATE=2026/04/02

REM Outbound time code: 1~36, maps to 00:00~23:30
REM Default 10 = around 09:00
set OUTBOUND_TIME=25

REM Adult ticket count: 1~10
set TICKETS=2

REM Train selection fallback: 1 = first available (used when no time range match)
set TRAIN_SELECTION=1

REM Preferred departure time range (HH:MM format, picks first train in range)
set PREFERRED_TIME_START=17:00
set PREFERRED_TIME_END=18:00

REM Personal ID number
set ID_NUMBER=S125124883

REM Phone number
set PHONE=0912345678

REM LINE Push Notification (訂票成功時推送結果到 LINE)
set LINE_CHANNEL_ACCESS_TOKEN=ZKOT/fZ30nFQlVV2iSJyDpMCm/4LhzxnUdez/a91cPXgmE1YTid4zQUj0l2jBChrTnqZeJ9bwBs6mG8SB+rUbQ+WPlcukW0WEjrSIJV/ZHgkQidmrp3IYhexiRl/5QLeVRxtTAUJCLPkVtTNFPYP9wdB04t89/1O/w1cDnyilFU=
set LINE_NOTIFY_USER_ID=Uefe534b61be72ce77c7afa29904d21e4

REM ==========================================

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

REM 確認 ddddocr 已安裝（驗證碼自動辨識）
REM 如已安裝可跳過，首次使用請手動執行: pip install ddddocr
pip show ddddocr >nul 2>&1 || pip install ddddocr

REM 執行自動化訂票
python auto_book.py

REM 被 LINE Bot 呼叫時不需要 pause
if "%LINE_NOTIFY_USER_ID%"=="" pause
