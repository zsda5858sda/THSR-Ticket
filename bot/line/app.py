"""
LINE Bot + THSR 自動訂票整合（互動版）
- Quick Reply 按鈕選單
- 多步驟參數設定（站別、日期、時間、票數）
- REST API：POST /api/stop, GET /api/status
- 訂票成功時透過 LINE Push Message 推送結果
"""

import os
import subprocess
import threading
from typing import Optional, List, Tuple, Dict, Any
from flask import Flask, request, abort, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError

app = Flask(__name__)

# ============================================================
# Token & Secret（從環境變數讀取）
# ============================================================
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")

# THSR 自動訂票程式路徑（相對於此檔案位置，往上兩層即為專案根目錄）
THSR_PROJECT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
AUTO_BOOK_SCRIPT = os.path.join(THSR_PROJECT_DIR, "auto_book.py")

# Python 路徑（雲端環境直接用系統 python）
THSR_PYTHON = os.environ.get("THSR_PYTHON_PATH", "python")

handler = WebhookHandler(CHANNEL_SECRET)
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)

# ============================================================
# 車站 & 時間常數
# ============================================================
STATIONS = {
    "1": "南港", "2": "台北", "3": "板橋", "4": "桃園",
    "5": "新竹", "6": "苗栗", "7": "台中", "8": "彰化",
    "9": "雲林", "10": "嘉義", "11": "台南", "12": "左營",
}

# AVAILABLE_TIME_TABLE 對應的可讀時間 (index 1-based)
TIME_SLOTS = [
    ("1", "00:01"), ("2", "00:30"), ("3", "06:00"), ("4", "06:30"),
    ("5", "07:00"), ("6", "07:30"), ("7", "08:00"), ("8", "08:30"),
    ("9", "09:00"), ("10", "09:30"), ("11", "10:00"), ("12", "10:30"),
    ("13", "11:00"), ("14", "11:30"), ("15", "12:00"), ("16", "12:30"),
    ("17", "13:00"), ("18", "13:30"), ("19", "14:00"), ("20", "14:30"),
    ("21", "15:00"), ("22", "15:30"), ("23", "16:00"), ("24", "16:30"),
    ("25", "17:00"), ("26", "17:30"), ("27", "18:00"), ("28", "18:30"),
    ("29", "19:00"), ("30", "19:30"), ("31", "20:00"), ("32", "20:30"),
    ("33", "21:00"), ("34", "21:30"), ("35", "22:00"), ("36", "22:30"),
    ("37", "23:00"), ("38", "23:30"),
]

# ============================================================
# 訂票參數（使用者可透過對話設定）
# ============================================================
_booking_params: Dict[str, str] = {
    "SKIP_HISTORY": "1",
    "START_STATION": "4",
    "DEST_STATION": "11",
    "OUTBOUND_DATE": "2026/04/02",
    "OUTBOUND_TIME": "25",
    "TICKETS": "2",
    "PREFERRED_TIME_START": "17:00",
    "PREFERRED_TIME_END": "18:00",
    "TRAIN_SELECTION": "1",
    "ID_NUMBER": "S125124883",
    "PHONE": "0912345678",
    "LINE_CHANNEL_ACCESS_TOKEN": CHANNEL_ACCESS_TOKEN,
    "LINE_NOTIFY_USER_ID": LINE_USER_ID,
}

# ============================================================
# 使用者對話狀態
# ============================================================
# state:
#   None         -> 無狀態（正常模式）
#   "start_stn"  -> 等候選擇啟程站
#   "dest_stn"   -> 等候選擇到達站
#   "date"       -> 等候輸入日期
#   "time"       -> 等候選擇出發時間（上午/下午/晚上）
#   "time_pick"  -> 等候選擇具體時間
#   "tickets"    -> 等候選擇票數
#   "confirm"    -> 等候確認
_user_state: Dict[str, Optional[str]] = {}


def _get_state(user_id: str) -> Optional[str]:
    return _user_state.get(user_id)


def _set_state(user_id: str, state: Optional[str]) -> None:
    if state is None:
        _user_state.pop(user_id, None)
    else:
        _user_state[user_id] = state


# ============================================================
# Quick Reply 工具函數
# ============================================================
def _qr(label: str, text: Optional[str] = None) -> QuickReplyItem:
    """建立一個 Quick Reply 按鈕"""
    return QuickReplyItem(action=MessageAction(label=label, text=text or label))


def _make_menu_message() -> TextMessage:
    """產生功能選單訊息"""
    return TextMessage(
        text="請選擇功能：",
        quick_reply=QuickReply(items=[
            _qr("🚄 設定參數", "設定參數"),
            _qr("▶️ 啟動訂票", "啟動訂票"),
            _qr("⏹ 停止訂票", "停止訂票"),
            _qr("📊 訂票狀態", "訂票狀態"),
            _qr("📋 查看參數", "查看參數"),
        ]),
    )


def _make_station_qr(prefix: str, exclude: Optional[str] = None) -> QuickReply:
    """產生車站選擇的 Quick Reply（12 站），可排除指定站"""
    items = [_qr(f"{name}", f"{prefix}{code}")
             for code, name in STATIONS.items() if code != exclude]
    return QuickReply(items=items)


def _make_time_period_qr() -> QuickReply:
    """產生時段選擇（分上午/下午/晚上，避免按鈕太多）"""
    return QuickReply(items=[
        _qr("🌅 早上 06-09", "時段_早上"),
        _qr("☀️ 上午 09-12", "時段_上午"),
        _qr("🌤 下午 12-15", "時段_下午A"),
        _qr("🌇 下午 15-18", "時段_下午B"),
        _qr("🌙 晚上 18-21", "時段_晚上A"),
        _qr("🌑 晚上 21-00", "時段_晚上B"),
    ])


def _make_time_pick_qr(period: str) -> QuickReply:
    """根據選擇的時段，列出具體時間選項"""
    ranges = {
        "早上":  [s for s in TIME_SLOTS if "06:" in s[1] or "07:" in s[1] or "08:" in s[1]],
        "上午":  [s for s in TIME_SLOTS if "09:" in s[1] or "10:" in s[1] or "11:" in s[1]],
        "下午A": [s for s in TIME_SLOTS if "12:" in s[1] or "13:" in s[1] or "14:" in s[1]],
        "下午B": [s for s in TIME_SLOTS if "15:" in s[1] or "16:" in s[1] or "17:" in s[1]],
        "晚上A": [s for s in TIME_SLOTS if "18:" in s[1] or "19:" in s[1] or "20:" in s[1]],
        "晚上B": [s for s in TIME_SLOTS if "21:" in s[1] or "22:" in s[1] or "23:" in s[1] or "00:" in s[1]],
    }
    slots = ranges.get(period, [])
    items = [_qr(f"{time_str}", f"選時間_{code}_{time_str}") for code, time_str in slots]
    return QuickReply(items=items)


def _make_ticket_qr() -> QuickReply:
    """產生票數選擇 (1-10)"""
    items = [_qr(f"{i}張", f"票數_{i}") for i in range(1, 11)]
    return QuickReply(items=items)


def _get_params_summary() -> str:
    """取得目前參數摘要"""
    start = STATIONS.get(_booking_params["START_STATION"], "?")
    dest = STATIONS.get(_booking_params["DEST_STATION"], "?")
    time_code = _booking_params["OUTBOUND_TIME"]
    time_str = next((t[1] for t in TIME_SLOTS if t[0] == time_code), time_code)
    pref_start = _booking_params.get("PREFERRED_TIME_START", "")
    pref_end = _booking_params.get("PREFERRED_TIME_END", "")

    lines = [
        "📋 目前訂票參數：",
        f"  🚉 啟程站：{start}",
        f"  🚉 到達站：{dest}",
        f"  📅 出發日期：{_booking_params['OUTBOUND_DATE']}",
        f"  🕐 出發時間：{time_str}",
    ]
    if pref_start and pref_end:
        lines.append(f"  ⏰ 偏好時段：{pref_start}~{pref_end}")
    lines.append(f"  👤 票數：{_booking_params['TICKETS']}")
    lines.append(f"  🪪 身分證：{_booking_params.get('ID_NUMBER', '未設定')}")
    lines.append(f"  📱 手機：{_booking_params.get('PHONE', '未設定')}")
    return "\n".join(lines)


# ============================================================
# 對話狀態機
# ============================================================
def _handle_setup_flow(user_id: str, text: str) -> List[TextMessage]:
    """處理多步驟參數設定流程，回傳要回覆的訊息列表"""
    state = _get_state(user_id)

    # --- 開始設定 ---
    if state is None and text == "設定參數":
        _set_state(user_id, "start_stn")
        return [TextMessage(
            text="請選擇 🚉 啟程站：",
            quick_reply=_make_station_qr("啟程_"),
        )]

    # --- 選啟程站 ---
    if state == "start_stn" and text.startswith("啟程_"):
        code = text.replace("啟程_", "")
        if code in STATIONS:
            _booking_params["START_STATION"] = code
            _set_state(user_id, "dest_stn")
            return [TextMessage(
                text=f"啟程站：{STATIONS[code]} ✅\n\n請選擇 🚉 到達站：",
                quick_reply=_make_station_qr("到達_", exclude=code),
            )]

    # --- 選到達站 ---
    if state == "dest_stn" and text.startswith("到達_"):
        code = text.replace("到達_", "")
        if code in STATIONS:
            _booking_params["DEST_STATION"] = code
            _set_state(user_id, "date")
            return [TextMessage(
                text=f"到達站：{STATIONS[code]} ✅\n\n請輸入 📅 出發日期：\n格式：YYYY/MM/DD\n例如：2026/04/02",
            )]

    # --- 輸入日期 ---
    if state == "date":
        import datetime
        parts = text.split("/")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            try:
                input_date = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
            except ValueError:
                return [TextMessage(text="❌ 無效的日期，請重新輸入\n格式：YYYY/MM/DD")]
            today = datetime.date.today()
            if input_date < today:
                return [TextMessage(
                    text=f"❌ 出發日期不能早於今天（{today.strftime('%Y/%m/%d')}）\n請重新輸入：",
                )]
            _booking_params["OUTBOUND_DATE"] = text
            _set_state(user_id, "time")
            return [TextMessage(
                text=f"出發日期：{text} ✅\n\n請選擇 🕐 偏好出發時段：",
                quick_reply=_make_time_period_qr(),
            )]
        else:
            return [TextMessage(
                text="❌ 日期格式不正確，請用 YYYY/MM/DD 格式\n例如：2026/04/02",
            )]

    # --- 選時段 ---
    if state == "time" and text.startswith("時段_"):
        period = text.replace("時段_", "")
        _set_state(user_id, "time_pick")
        return [TextMessage(
            text="請選擇具體出發時間：",
            quick_reply=_make_time_pick_qr(period),
        )]

    # --- 選具體時間 ---
    if state == "time_pick" and text.startswith("選時間_"):
        parts = text.replace("選時間_", "").split("_")
        if len(parts) == 2:
            code, time_str = parts
            _booking_params["OUTBOUND_TIME"] = code
            _booking_params["PREFERRED_TIME_START"] = time_str

            # 結束時間設為選擇時間 +1 小時（簡化）
            hour = int(time_str.split(":")[0])
            end_hour = min(hour + 1, 23)
            _booking_params["PREFERRED_TIME_END"] = f"{end_hour:02d}:{time_str.split(':')[1]}"

            _set_state(user_id, "tickets")
            return [TextMessage(
                text=f"出發時間：{time_str} ✅\n\n請選擇 👤 票數：",
                quick_reply=_make_ticket_qr(),
            )]

    # --- 選票數 ---
    if state == "tickets" and text.startswith("票數_"):
        num = text.replace("票數_", "")
        if num.isdigit() and 1 <= int(num) <= 10:
            _booking_params["TICKETS"] = num
            _set_state(user_id, "id_number")
            return [TextMessage(
                text=f"票數：{num}張 ✅\n\n請輸入 🪪 身分證字號：\n（用於取票，例如：A123456789）",
            )]

    # --- 輸入身分證字號 ---
    if state == "id_number":
        import re
        if re.match(r'^[A-Z][12]\d{8}$', text.upper()):
            _booking_params["ID_NUMBER"] = text.upper()
            _set_state(user_id, "phone")
            return [TextMessage(
                text=f"身分證：{text.upper()} ✅\n\n請輸入 📱 手機號碼：\n（用於取票，例如：0912345678）",
            )]
        else:
            return [TextMessage(
                text="❌ 身分證字號格式不正確\n格式：1個英文字母 + 9個數字\n例如：A123456789",
            )]

    # --- 輸入手機號碼 ---
    if state == "phone":
        import re
        cleaned = text.replace("-", "").replace(" ", "")
        if re.match(r'^09\d{8}$', cleaned):
            _booking_params["PHONE"] = cleaned
            _set_state(user_id, "confirm")
            summary = _get_params_summary()
            return [TextMessage(
                text=f"手機：{cleaned} ✅\n\n{summary}",
                quick_reply=QuickReply(items=[
                    _qr("✅ 確認並訂票", "確認訂票"),
                    _qr("🔄 重新設定", "設定參數"),
                    _qr("💾 僅儲存", "儲存參數"),
                ]),
            )]
        else:
            return [TextMessage(
                text="❌ 手機號碼格式不正確\n格式：09 開頭共 10 碼\n例如：0912345678",
            )]

    # --- 確認 ---
    if state == "confirm":
        if text == "確認訂票":
            _set_state(user_id, None)
            ok, msg = _start_booking()
            return [TextMessage(text=msg)]
        elif text == "儲存參數":
            _set_state(user_id, None)
            return [TextMessage(
                text="💾 參數已儲存！可隨時用「啟動訂票」開始。",
                quick_reply=QuickReply(items=[
                    _qr("▶️ 啟動訂票", "啟動訂票"),
                    _qr("📋 查看參數", "查看參數"),
                ]),
            )]

    # 如果在設定流程中收到不認識的訊息，重置狀態
    if state is not None:
        _set_state(user_id, None)
        return [TextMessage(
            text="⚠️ 參數設定已取消。",
            quick_reply=QuickReply(items=[
                _qr("🚄 設定參數", "設定參數"),
                _qr("📋 查看參數", "查看參數"),
            ]),
        )]

    return []


# ============================================================
# 子程序管理
# ============================================================
_process: Optional[subprocess.Popen] = None
_process_lock = threading.Lock()
_output_lines: List[str] = []


def _start_booking() -> Tuple[bool, str]:
    """啟動訂票子程序"""
    global _process, _output_lines
    with _process_lock:
        if _process and _process.poll() is None:
            return False, "訂票程序已在執行中，請先停止再重新啟動。"

        _output_lines = []
        env = os.environ.copy()
        env.update(_booking_params)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        _process = subprocess.Popen(
            [THSR_PYTHON, AUTO_BOOK_SCRIPT],
            cwd=THSR_PROJECT_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
        )

        t = threading.Thread(target=_collect_output, daemon=True)
        t.start()

        summary = _get_params_summary()
        return True, f"🚄 訂票程序已啟動！\n\n{summary}"


def _stop_booking() -> str:
    """停止訂票子程序"""
    global _process
    with _process_lock:
        if not _process or _process.poll() is not None:
            return "目前沒有訂票程序在執行。"
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
        _process = None
        return "🛑 訂票程序已停止。"


def _get_status() -> Dict[str, Any]:
    """取得目前訂票程序狀態"""
    with _process_lock:
        if not _process:
            return {"running": False, "message": "目前沒有訂票程序在執行。"}
        if _process.poll() is not None:
            exit_code = _process.returncode
            last_lines = _output_lines[-10:] if _output_lines else []
            return {
                "running": False,
                "message": f"訂票程序已結束（exit code: {exit_code}）",
                "last_output": last_lines,
            }
        last_lines = _output_lines[-10:] if _output_lines else []
        return {
            "running": True,
            "message": "訂票程序執行中...",
            "last_output": last_lines,
        }


def _decode_line(raw: bytes) -> str:
    """嘗試 UTF-8 解碼，失敗則 fallback 到 cp950"""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp950", errors="replace")


def _collect_output():
    """背景執行緒：收集子程序的 stdout"""
    global _process
    try:
        for raw_line in _process.stdout:
            line = _decode_line(raw_line).rstrip("\r\n")
            _output_lines.append(line)
            print(f"[THSR] {line}")
    except Exception:
        pass


# ============================================================
# Health Check（Render 使用）
# ============================================================
@app.route("/", methods=["GET"])
def health_check():
    return "OK", 200


# ============================================================
# LINE Webhook
# ============================================================
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    app.logger.info("Request body: %s", body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.warning("Invalid signature.")
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    messages = []  # type: List[TextMessage]

    # 先檢查是否在設定流程中
    if _get_state(user_id) is not None or text == "設定參數":
        messages = _handle_setup_flow(user_id, text)
    elif text == "啟動訂票":
        ok, msg = _start_booking()
        messages = [TextMessage(text=msg)]
    elif text == "停止訂票":
        messages = [TextMessage(text=_stop_booking())]
    elif text == "訂票狀態":
        status = _get_status()
        reply_text = status["message"]
        if status.get("last_output"):
            reply_text += "\n\n📄 最近輸出：\n" + "\n".join(status["last_output"])
        messages = [TextMessage(text=reply_text)]
    elif text == "查看參數":
        messages = [TextMessage(text=_get_params_summary())]
    elif text in ("選單", "功能", "menu", "help"):
        messages = [_make_menu_message()]
    else:
        # 非指令 → 顯示功能選單
        messages = [_make_menu_message()]

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages,
            )
        )


# ============================================================
# REST API
# ============================================================
@app.route("/api/stop", methods=["POST"])
def api_stop():
    return jsonify({"message": _stop_booking()})


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(_get_status())


@app.route("/api/params", methods=["GET"])
def api_params():
    """查詢目前訂票參數"""
    safe_params = {k: v for k, v in _booking_params.items()
                   if k not in ("LINE_CHANNEL_ACCESS_TOKEN", "ID_NUMBER", "PHONE")}
    return jsonify(safe_params)


# ============================================================
# 啟動伺服器
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
