# docker build -t blk-hacking-ind-{name-lastname} .
# OS choice: python:3.11-slim (Debian-based Linux) for small image size, fast pulls, and stable security updates.
FROM python:3.11-slim

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY app ./app

USER app

EXPOSE 5477
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5477/health').read()"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5477", "--workers", "1"]
