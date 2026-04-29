FROM mcr.microsoft.com/playwright/python:v1.59.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

ENV DB_PATH=/data/tracker.db
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["python", "app.py"]
