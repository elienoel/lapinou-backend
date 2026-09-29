#!/bin/sh
set -e

if [ -n "$DB_HOST" ]; then
    echo "Waiting for database at $DB_HOST:${DB_PORT:-5432}..."
    until nc -z "$DB_HOST" "${DB_PORT:-5432}"; do
        sleep 1
    done
    echo "Database is up."
fi

python manage.py migrate --noinput

if [ "$DEBUG" != "True" ] && [ "$DEBUG" != "true" ] && [ "$DEBUG" != "1" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
