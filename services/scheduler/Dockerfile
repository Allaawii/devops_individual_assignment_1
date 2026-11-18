# Scheduler service image: Python 3.10 with the app, run by gunicorn as a non-root user.
FROM python:3.10-slim

# No .pyc files in the image, and log lines reach `docker logs` at once instead of being buffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first: Docker reuses this layer until requirements.txt changes, so code-only
# changes rebuild in seconds. pymssql's wheel already contains the FreeTDS driver.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what the service needs at runtime (tests and dev tools stay out of the image).
COPY app.py migrate.py ./
COPY scheduler/ scheduler/
COPY migrations/ migrations/

# Never run as root inside the container.
RUN useradd --create-home --uid 10001 app
USER app

# The commit the image was built from, reported by /health.
ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA} \
    PORT=8000
EXPOSE 8000

# One worker with 4 threads: one process holds the app, threads serve requests in parallel.
# --timeout 120: startup may wait about 90 s for a paused Azure SQL database to resume, and
# gunicorn kills a worker that stays silent longer than its timeout.
# "app:create_app()" calls the factory, so importing app.py never connects to the database.
# `exec` makes gunicorn the main process, so it receives the stop signal and shuts down cleanly.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120 'app:create_app()'"]
