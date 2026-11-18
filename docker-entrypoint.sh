
#!/bin/sh
set -eu

# For host-monitoring mode, the database is managed by Ubuntu.
# The container only reads the existing SQLite database.
if [ "${DB_READ_ONLY:-0}" = "1" ]; then
    echo "Using existing read-only host monitoring database."
else
    # Standalone container mode: initialize a local SQLite database.
    python -c "from database import init_database; init_database()"
fi

# Start Gunicorn as the container's main process
exec gunicorn --workers 2 --bind 0.0.0.0:5000 app:app
