FROM python:3.9-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ARG PORT=5000
ENV PORT=$PORT
EXPOSE $PORT

VOLUME /app/translated_files

CMD ["python", "translation_api.py"]