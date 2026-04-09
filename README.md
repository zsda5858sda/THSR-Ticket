# 🚄 高鐵訂票小幫手

**⚠️ 純研究用途，請勿用於不當用途 ⚠️**

以命令列介面快速訂購台灣高鐵車票。跳過網頁渲染，只保留核心訂購流程，大幅節省等待時間。

> 🦀 **Rust 新版本** 已推出，支援執行檔、早鳥票預訂、會員購票等功能 → [thsr-ticket-rs](https://github.com/BreezeWhite/thsr-ticket-rs)

---

## 功能一覽

### ✅ 互動式訂票 (`thsr_ticket/main.py`)

| 功能 | 狀態 |
|------|:----:|
| 選擇啟程 / 到達站 | ✅ |
| 選擇出發日期 / 時間 | ✅ |
| 選擇班次 | ✅ |
| 選擇成人票數 | ✅ |
| 輸入驗證碼 | ✅ |
| 輸入身分證字號 | ✅ |
| 輸入手機號碼 | ✅ |
| 保留輸入紀錄供下次快速選擇 | ✅ |

### 🤖 全自動訂票 (`auto_book.py`)

透過環境變數設定所有訂票參數，搭配 `run.bat` 一鍵執行：

- 驗證碼 OCR 自動辨識（[ddddocr](https://github.com/sml2h3/ddddocr)）
- 指定偏好出發時間範圍，自動選取最佳車次
- 訂票失敗自動重試（預設 30 秒間隔）
- 訂票成功時發送 **Windows 原生 Toast 通知**

---

## 安裝

### 前置需求

- Python 3.8+
- (自動訂票) `ddddocr`：驗證碼 OCR

### 方法一：pip 安裝（快速）

```bash
pip install git+https://github.com/BreezeWhite/THSR-Ticket.git

# 執行互動式訂票
thsr-ticket
```

### 方法二：Clone 原始碼

```bash
git clone https://github.com/BreezeWhite/THSR-Ticket.git
cd THSR-Ticket

python -m pip install -r requirements.txt

# 互動式訂票
python thsr_ticket/main.py
```

---

## 全自動訂票

### 快速開始

1. 編輯 `run.bat`，填入訂票參數（詳見下方參數表）
2. 雙擊 `run.bat` 即可執行

### 環境變數參數

| 變數 | 說明 | 範例 |
|------|------|------|
| `SKIP_HISTORY` | 跳過歷史紀錄選擇 (`1`=跳過) | `1` |
| `START_STATION` | 啟程站代碼 | `4` |
| `DEST_STATION` | 到達站代碼 | `11` |
| `OUTBOUND_DATE` | 出發日期 | `2026/04/02` |
| `OUTBOUND_TIME` | 出發時間代碼 (1\~36) | `25` |
| `TICKETS` | 成人票數 | `2` |
| `PREFERRED_TIME_START` | 偏好出發時間起 | `17:00` |
| `PREFERRED_TIME_END` | 偏好出發時間迄 | `18:00` |
| `TRAIN_SELECTION` | 備選車次序號 (無偏好時段命中時使用) | `1` |
| `ID_NUMBER` | 身分證字號 | `A123456789` |
| `PHONE` | 手機號碼 | `0912345678` |

### 車站代碼

| 代碼 | 站名 | 代碼 | 站名 |
|:----:|------|:----:|------|
| 1 | 南港 | 7 | 台中 |
| 2 | 台北 | 8 | 彰化 |
| 3 | 板橋 | 9 | 雲林 |
| 4 | 桃園 | 10 | 嘉義 |
| 5 | 新竹 | 11 | 台南 |
| 6 | 苗栗 | 12 | 左營 |

---

## 專案結構

```
THSR-Ticket/
├── thsr_ticket/           # 核心套件
│   ├── main.py            # 互動式訂票入口
│   ├── controller/        # 訂票流程控制
│   ├── model/             # 資料模型
│   ├── view/              # 顯示邏輯
│   ├── view_model/        # 資料解析
│   ├── configs/           # 設定與列舉
│   ├── remote/            # HTTP 請求
│   ├── ml/                # 驗證碼辨識模型
│   └── unittest/          # 單元測試
├── auto_book.py           # 全自動訂票腳本
├── run.bat                # Windows 一鍵執行
├── setup.py               # 套件安裝設定
├── requirements.txt       # Python 依賴
└── makefile               # 程式碼品質檢查 & 測試
```

---

## 開發

```bash
# 型別檢查 + lint + 測試
make all

# 個別執行
make check-mypy
make check-flake
make check-pylint
make test
```

---

## License

本專案僅供學術研究使用。
