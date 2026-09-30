# Dockerfile
FROM python:3.12-slim
 
WORKDIR /code
 
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
COPY . ./

EXPOSE 8080
 
CMD ["fastapi", "run", "./src/main.py", "--host", "0.0.0.0", "--port", "8080"]
