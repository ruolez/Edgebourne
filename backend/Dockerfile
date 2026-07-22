# ---- build stage: wheels only, kept out of the runtime image ----
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---- runtime stage ----
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY . .

EXPOSE 5000

# --preload imports the app once in the master (serializes migrations to a
# single run at startup); workers share it copy-on-write.
ENV GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4 \
    GUNICORN_TIMEOUT=120

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:5000 \
    --workers ${GUNICORN_WORKERS} \
    --threads ${GUNICORN_THREADS} \
    --timeout ${GUNICORN_TIMEOUT} \
    --worker-tmp-dir /dev/shm \
    --preload \
    'app:create_app()'"]
