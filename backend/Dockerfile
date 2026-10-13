FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./src/ ./src/
COPY ./data/ ./src/data/

EXPOSE 8080

CMD ["fastapi", "run", "src/main.py", "--host", "0.0.0.0", "--port", "8080"]
