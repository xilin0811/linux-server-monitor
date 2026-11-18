
# 1. Use an official Python runtime as the base image
FROM python:3.12-slim

# 2. Configure Python runtime behavior
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. Set the application's working directory
WORKDIR /app

# 4. Install Python dependencies first
COPY requirements.txt ./

RUN python -m pip install --no-cache-dir -r requirements.txt

# 5. Copy application source code
COPY app.py monitor.py database.py collect_once.py ./
COPY templates/ ./templates/
COPY static/ ./static/
COPY docker-entrypoint.sh ./docker-entrypoint.sh

# 6. Create a non-root user and writable database directory
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --no-create-home appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data

# 7. Run the application as a non-root user
USER appuser

# 8. Document the internal application port
EXPOSE 5000

# 9. Initialize the database, then start Gunicorn
CMD ["sh", "/app/docker-entrypoint.sh"]
