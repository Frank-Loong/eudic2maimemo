FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY eudic2maimemo ./eudic2maimemo

# 默认常驻：启动先同步一次，之后按 SYNC_INTERVAL_HOURS（默认 24）循环
ENTRYPOINT ["python", "-m", "eudic2maimemo"]
CMD ["serve"]
