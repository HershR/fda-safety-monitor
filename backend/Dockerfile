# Dockerfile
FROM python:3.13-slim
 
WORKDIR /src
 
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./src/ ./

EXPOSE 8080
 
CMD ["fastapi", "run", "./main.py", "--host", "0.0.0.0", "--port", "8080"]
