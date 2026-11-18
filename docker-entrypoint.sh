
#!/bin/sh
set -eu

# Initialize SQLite database and tables at container startup
python -c "from database import init_database; init_database()"

# Replace the shell with Gunicorn
exec gunicorn --workers 2 --bind 0.0.0.0:5000 app:app
