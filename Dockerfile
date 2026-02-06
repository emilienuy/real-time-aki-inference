FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
COPY model.joblib /app/model.joblib

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "-m", "src.main"]
