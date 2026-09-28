FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py index.html dashboard.css dashboard.js purchase-quotes.js mobile.html mobile.css mobile.js manifest.webmanifest sw.js icon-192.svg icon-512.svg ./

# 재고 DB가 저장될 볼륨 경로
ENV DB_PATH=/data/inventory.db
VOLUME ["/data"]

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:80/health')" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]
