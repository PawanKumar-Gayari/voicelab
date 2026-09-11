FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ENVIRONMENT=production \
    DEBUG=false

WORKDIR /app

COPY requirements.txt requirements-livekit.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-livekit.txt

COPY . .
RUN rm -rf .pytest_cache __pycache__ */__pycache__ tests/__pycache__ 2>/dev/null || true

RUN useradd --create-home --shell /usr/sbin/nologin voicelab \
    && chown -R voicelab:voicelab /app
USER voicelab

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
