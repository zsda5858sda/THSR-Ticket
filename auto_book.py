import os
import time
import subprocess
import tempfile
from thsr_ticket.controller.booking_flow import BookingFlow
from thsr_ticket.controller.first_page_flow import FirstPageFlow
from thsr_ticket.controller.confirm_train_flow import ConfirmTrainFlow
from thsr_ticket.controller.confirm_ticket_flow import ConfirmTicketFlow
from thsr_ticket.configs.web.enums import TicketType
from thsr_ticket.view_model.error_feedback import ErrorFeedback
import thsr_ticket.view.common as view_common
import thsr_ticket.controller.first_page_flow as first_page_module

# ======== 驗證碼自動辨識 ========
try:
    import ddddocr
    _ocr = ddddocr.DdddOcr(show_ad=False)
except ImportError:
    _ocr = None
    print("[警告] 未安裝 ddddocr，驗證碼將改為手動輸入。請執行: pip install ddddocr")

def _auto_input_security_code(img_resp: bytes) -> str:
    if _ocr is not None:
        result = _ocr.classification(img_resp)
        print(f"驗證碼自動辨識結果: {result}")
        return result
    else:
        # fallback: 手動輸入
        from PIL import Image
        import io
        print("輸入驗證碼：")
        image = Image.open(io.BytesIO(img_resp))
        image.show()
        return input()

# 替換模組層級的 _input_security_code
first_page_module._input_security_code = _auto_input_security_code

# 攔截並替換原本的輸入函數，改由環境變數讀取
original_history_info = view_common.history_info
def mock_history_info(hists, select=True):
    if os.getenv("SKIP_HISTORY") == "1":
        print("自動跳過歷史紀錄選擇")
        return None
    return original_history_info(hists, select)
view_common.history_info = mock_history_info

original_select_station = FirstPageFlow.select_station
def mock_select_station(self, travel_type, default_value=None):
    if travel_type == '啟程' and os.getenv("START_STATION"):
        val = int(os.getenv("START_STATION"))
        print(f"自動選擇啟程站: {val}")
        return val
    if travel_type == '到達' and os.getenv("DEST_STATION"):
        val = int(os.getenv("DEST_STATION"))
        print(f"自動選擇到達站: {val}")
        return val
    return original_select_station(self, travel_type, default_value)
FirstPageFlow.select_station = mock_select_station

original_select_date = FirstPageFlow.select_date
def mock_select_date(self, date_type):
    if date_type == '出發' and os.getenv("OUTBOUND_DATE"):
        val = os.getenv("OUTBOUND_DATE")
        print(f"自動選擇出發日期: {val}")
        return val
    return original_select_date(self, date_type)
FirstPageFlow.select_date = mock_select_date

original_select_time = FirstPageFlow.select_time
def mock_select_time(self, time_type, default_value=10):
    val = os.getenv("OUTBOUND_TIME")
    if time_type == '啟程' and val:
        print(f"自動選擇出發時間: 選項 {val}")
        from thsr_ticket.configs.common import AVAILABLE_TIME_TABLE
        return AVAILABLE_TIME_TABLE[int(val)-1]
    return original_select_time(self, time_type, default_value)
FirstPageFlow.select_time = mock_select_time

original_select_ticket_num = FirstPageFlow.select_ticket_num
def mock_select_ticket_num(self, ticket_type, default_ticket_num=1):
    val = os.getenv("TICKETS")
    if ticket_type == TicketType.ADULT and val:
        print(f"自動選擇成人票數: {val}")
        return f"{val}{ticket_type.value}"
    return original_select_ticket_num(self, ticket_type, default_ticket_num)
FirstPageFlow.select_ticket_num = mock_select_ticket_num

original_select_trains = ConfirmTrainFlow.select_available_trains
def mock_select_trains(self, trains, default_value=1):
    time_start = os.getenv("PREFERRED_TIME_START")  # e.g. "17:00"
    time_end = os.getenv("PREFERRED_TIME_END")      # e.g. "18:00"

    # 先印出所有可選車次
    for idx, train in enumerate(trains, 1):
        print(
            f'{idx}. {train.id:>4} {train.depart:>3}~{train.arrive} {train.travel_time:>3} '
            f'{train.discount_str}'
        )

    if time_start and time_end:
        matched = [t for t in trains if time_start <= t.depart <= time_end]
        if matched:
            selected = matched[0]
            print(f"自動選擇時間範圍 {time_start}~{time_end} 內的車次: {selected.id} ({selected.depart})")
            return selected.form_value
        else:
            print(f"[警告] 時間範圍 {time_start}~{time_end} 內無可選車次，改選第一班")

    val = os.getenv("TRAIN_SELECTION", "1")
    idx = int(val)
    print(f"自動選擇第 {idx} 個車次")
    return trains[idx-1].form_value
ConfirmTrainFlow.select_available_trains = mock_select_trains

original_set_pid = ConfirmTicketFlow.set_personal_id
def mock_set_pid(self):
    val = os.getenv("ID_NUMBER")
    if val:
        print(f"自動輸入身分證字號: {val}")
        return val
    return original_set_pid(self)
ConfirmTicketFlow.set_personal_id = mock_set_pid

original_set_phone = ConfirmTicketFlow.set_phone_num
def mock_set_phone(self):
    val = os.getenv("PHONE")
    if val:
        print(f"自動輸入手機號碼: {val}")
        return val
    return original_set_phone(self)
ConfirmTicketFlow.set_phone_num = mock_set_phone

# ======== Windows 原生 Toast 通知 ========
def _show_windows_toast(title: str, body: str):
    """使用 PowerShell 呼叫 Windows 原生 Toast Notification"""
    try:
        body_xml = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "&#10;")
        title_xml = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # 使用 here-string 避免引號問題
        ps_lines = [
            '[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null',
            '[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null',
            '$template = @"',
            f'<toast><visual><binding template="ToastGeneric"><text>{title_xml}</text><text>{body_xml}</text></binding></visual><audio src="ms-winsoundevent:Notification.Default"/></toast>',
            '"@',
            '$xml = New-Object Windows.Data.Xml.Dom.XmlDocument',
            '$xml.LoadXml($template)',
            '$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)',
            '[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("THSR-Ticket").Show($toast)',
        ]
        ps_script = "\r\n".join(ps_lines)

        # 寫到暫存檔避免 cmd 編碼問題
        ps_path = os.path.join(tempfile.gettempdir(), "thsr_toast.ps1")
        with open(ps_path, "w", encoding="utf-8-sig") as f:
            f.write(ps_script)

        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_path],
            capture_output=True, text=True, timeout=15
        )

        try:
            os.unlink(ps_path)
        except OSError:
            pass

        if result.returncode == 0 and not result.stderr.strip():
            print("已發送 Windows 通知！")
        else:
            print(f"通知發送失敗: {result.stderr.strip()}")
    except Exception as e:
        print(f"通知發送失敗（不影響訂票結果）: {e}")


# ======== LINE Push Message 通知 ========
def _send_line_push(title: str, body: str):
    """透過 LINE Messaging API 推送訂票結果"""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.getenv("LINE_NOTIFY_USER_ID")
    if not token or not user_id:
        print("[LINE 通知] 未設定 LINE 環境變數，跳過推送。")
        return

    import requests as req
    try:
        resp = req.post(
            "https://api.line.me/v2/bot/message/push",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json={
                "to": user_id,
                "messages": [{"type": "text", "text": f"{title}\n\n{body}"}],
            },
            timeout=10,
        )
        if resp.status_code == 200:
            print("已發送 LINE 通知！")
        else:
            print(f"LINE 通知發送失敗: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"LINE 通知發送失敗（不影響訂票結果）: {e}")

RETRY_DELAY = 30  # seconds

if __name__ == "__main__":
    attempt = 0
    while True:
        attempt += 1
        print(f"\n{'='*40}")
        print(f"第 {attempt} 次嘗試訂票...")
        print(f"{'='*40}")
        try:
            flow = BookingFlow()
            if os.getenv("SKIP_HISTORY") != "1":
                flow.show_history()

            book_resp, book_model = FirstPageFlow(client=flow.client, record=flow.record).run()
            errors = ErrorFeedback().parse(book_resp.content)
            if errors:
                err_msgs = [e.msg for e in errors]
                print(f"錯誤: {'; '.join(err_msgs)}")
                print(f"{RETRY_DELAY} 秒後自動重試...")
                time.sleep(RETRY_DELAY)
                continue

            train_resp, train_model = ConfirmTrainFlow(flow.client, book_resp).run()
            errors = ErrorFeedback().parse(train_resp.content)
            if errors:
                err_msgs = [e.msg for e in errors]
                print(f"錯誤: {'; '.join(err_msgs)}")
                print(f"{RETRY_DELAY} 秒後自動重試...")
                time.sleep(RETRY_DELAY)
                continue

            ticket_resp, ticket_model = ConfirmTicketFlow(flow.client, train_resp, flow.record).run()
            errors = ErrorFeedback().parse(ticket_resp.content)
            if errors:
                err_msgs = [e.msg for e in errors]
                print(f"錯誤: {'; '.join(err_msgs)}")
                print(f"{RETRY_DELAY} 秒後自動重試...")
                time.sleep(RETRY_DELAY)
                continue

            from thsr_ticket.view_model.booking_result import BookingResult
            from thsr_ticket.view.web.show_booking_result import ShowBookingResult
            result_model = BookingResult().parse(ticket_resp.content)
            ShowBookingResult().show(result_model)
            print("\n請使用官方提供的管道完成後續付款以及取票!!")
            flow.db.save(book_model, ticket_model)

            # Windows 原生通知
            ticket = result_model[0]
            now_str = time.strftime("%Y/%m/%d %H:%M:%S")
            toast_title = f"高鐵訂票成功！訂位代號: {ticket.id}"
            toast_body = (
                f"訂票時間: {now_str}\n"
                f"{ticket.date} {ticket.depart_time}→{ticket.arrival_time}\n"
                f"{ticket.start_station}→{ticket.dest_station} 車次{ticket.train_id}\n"
                f"票數: {ticket.ticket_num_info}  總價: {ticket.price}"
            )
            _show_windows_toast(toast_title, toast_body)
            _send_line_push(toast_title, toast_body)
            break

        except Exception as e:
            print(f"發生例外錯誤: {e}")
            print(f"{RETRY_DELAY} 秒後自動重試...")
            time.sleep(RETRY_DELAY)
