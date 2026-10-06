FROM python:3.12-slim
WORKDIR /srv
RUN pip install --no-cache-dir fastapi uvicorn httpx
COPY main.py .
EXPOSE 8085
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8085"]
