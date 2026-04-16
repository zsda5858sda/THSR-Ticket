FROM python:3.11-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 先複製 requirements 以利用 Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安裝 LINE Bot 額外依賴
RUN pip install --no-cache-dir \
    flask \
    gunicorn \
    line-bot-sdk \
    ddddocr

# 複製專案程式碼
COPY . .

# 安裝 thsr_ticket 套件（editable mode）
RUN pip install -e .

EXPOSE 10000

# 使用 gunicorn 啟動（production grade）
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "4", "--timeout", "120", "bot.line.app:app"]
