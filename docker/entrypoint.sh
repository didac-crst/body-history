#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Create bootstrap superuser when credentials are provided and no users exist.
python manage.py bootstrap_admin || true

exec "$@"
