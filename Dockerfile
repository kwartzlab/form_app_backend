FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port 8080 (Cloud Run default)
EXPOSE 8080

# Fail the container health check if the app stops answering (e.g. all worker
# threads wedged). Paired with the autoheal container + "autoheal=true" label
# in the stack, this restarts the forms automatically instead of needing a
# manual VM reboot.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=8)" || exit 1

# Run with gunicorn
# --workers 2: one wedged worker degrades service instead of killing it
# --max-requests + jitter: recycle workers periodically so slowly-leaked
#   stuck threads can't accumulate for weeks
CMD exec gunicorn --bind :8080 --workers 2 --threads 8 --timeout 120 \
    --max-requests 500 --max-requests-jitter 50 --graceful-timeout 30 app:app
