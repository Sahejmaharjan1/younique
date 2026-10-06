FROM python:3.12-slim
WORKDIR /srv
COPY backend /srv/backend
COPY connectors /srv/connectors
RUN pip install --no-cache-dir /srv/connectors/_sdk /srv/backend
EXPOSE 8000
CMD ["uvicorn", "younique.main_api:app", "--host", "0.0.0.0", "--port", "8000"]
