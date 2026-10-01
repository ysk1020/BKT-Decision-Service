FROM python:3.10-slim

WORKDIR /app

COPY requirements-service.txt .
RUN pip install --no-cache-dir -r requirements-service.txt

COPY app/ ./app/

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
