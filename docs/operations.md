# Operations

## Deploy / restart

```sh
cd /srv/satellite/apps/body-history
docker compose up -d --build
```

Service name / container: `body-history`  
Host port mapping: `3060:8000`

Logs:

```sh
docker compose logs -f --tail 100
```

## Secrets

Copy `.env.example` to the host secrets file (never commit the real file):

```text
/srv/satellite/secrets/body-history.env
```

Required keys (names only):

```text
DJANGO_SECRET_KEY
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
POSTGRES_HOST
POSTGRES_PORT
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
```

Database identity for this app:

```text
POSTGRES_DB=body_history
POSTGRES_USER=body_history_app
```

Do not reuse a personal UI username as `POSTGRES_USER`.

After editing secrets:

```sh
docker compose up -d --force-recreate
```

## Bootstrap first UI user

Optional one-shot env vars in the secrets file:

```text
DJANGO_BOOTSTRAP_ADMIN_USER=yourname
DJANGO_BOOTSTRAP_ADMIN_PASSWORD=replace-me
DJANGO_BOOTSTRAP_ADMIN_EMAIL=optional@example.com
```

The entrypoint creates that user only when the auth user table is empty.  
After first login works, remove `DJANGO_BOOTSTRAP_ADMIN_PASSWORD` from the secrets file and recreate the container.

Manual alternative:

```sh
docker compose exec body-history python manage.py createsuperuser
```

## Import Excel workbook

```mermaid
flowchart TD
  place["Place workbook under<br/>data imports directory"] --> ui["Sign in → Excel import"]
  ui --> dry["Dry run"]
  dry --> review["Review verification report"]
  review --> import["Import<br/>idempotent by file hash"]
```

1. Place the workbook at `/srv/satellite/data/body-history/imports/Pes.xlsx` (outside git).
2. Sign in → **Excel import**.
3. **Dry run** first; confirm unique dates / ranges.
4. **Import** (idempotent by file hash for the same profile).

Additional dated text blocks (if used) also belong under the data `imports/` directory, not in the git tree.

## Phone quick entry

URL path: `/manual_import/`

```mermaid
flowchart LR
  w["Weight"] --> f["Fat %"]
  f --> m["Muscle %"]
  m --> d["Date"]
  d --> s["Review and save"]
```

Intended for “Add to Home Screen”. No links to other app features on that page.  
Still requires Django login; trusted-device cookie avoids repeated passwords on known phones.

## Tests

```sh
docker compose run --rm --entrypoint "" -e BODY_HISTORY_USE_SQLITE=1 body-history pytest
```

## Database

Logical database: `body_history`  
App schema: `body` (via PostgreSQL `search_path`)  
Backups: whole-cluster PostgreSQL NAS job (not this app).
