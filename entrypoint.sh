#!/bin/bash
set -e

# We rely on the migration service in docker-compose for migrations in a Compose setup.
# However, if run standalone (without compose), this entrypoint will just start Uvicorn.
# The user specifically requested: "Do NOT run alembic upgrade head from the backend container's normal entrypoint.sh. Keep backend startup as Uvicorn only."

if [ "$#" -eq 0 ]; then
    echo "Starting JustiAssist backend via Uvicorn..."
    exec uvicorn app:app --host 0.0.0.0 --port 8000 --proxy-headers
else
    echo "Executing command: $@"
    exec "$@"
fi
