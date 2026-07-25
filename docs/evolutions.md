# Evolutions (as built)

Product and platform changes since the original MVP / Body Compass specs.
This is the short “what we decided later” log. Detailed how-to stays in
[operations.md](operations.md), [privacy.md](privacy.md), and
[architecture.md](architecture.md).

## Identity and ownership

- **UI users ≠ database credentials.** Django auth users (hashed passwords in
  the app DB) are managed with `manage_body_user`. `POSTGRES_*` in the secrets
  file is only for the DB connection.
- **One body profile per UI user.** `Profile.user` is a `OneToOneField`
  (`related_name=body_profile`). No household multi-profile switcher, no
  “Add profile” UI.
- All measurements, targets, imports, exports, and Compass data hang off that
  single profile and are scoped to `request.user`.

## Auth, session, CSRF

- Session cookie name: `bh_sessionid`. CSRF secret lives in the session
  (`CSRF_USE_SESSIONS=1`). Legacy `sessionid` / `csrftoken` cookies are cleared
  on login/logout to avoid HTTP↔HTTPS conflicts.
- Behind Cloudflare: `DJANGO_BEHIND_PROXY=1` (default) trusts
  `X-Forwarded-Proto`. Prefer HTTPS + `DJANGO_SECURE_COOKIES=1`.
- Stale login POST → redirect to `/login/?expired=1` with a fresh form (no raw
  Django 403 for that path).
- **Logout** always revokes this browser’s trusted-device token and clears the
  cookie (otherwise middleware would sign you straight back in).

## UI users CLI

```sh
docker compose exec body-history python manage.py manage_body_user add --superuser
docker compose exec body-history python manage.py manage_body_user reset-password --username …
docker compose exec body-history python manage.py manage_body_user deactivate --username …
docker compose exec body-history python manage.py manage_body_user activate --username …
docker compose exec body-history python manage.py manage_body_user list
```

- Interactive `add` by default (`getpass`); optional `--password-env` /
  `--non-interactive` for automation.
- Never pass a plaintext password as a positional CLI argument.
- Does not touch secrets env or Postgres roles.

## Body Compass charts

- **Opportunity Impact** track is absolute **0–100 alignment**. Each row shows
  `today → simulated` plus `+gain`. Green segment is the move from current
  alignment to the counterfactual score (not a bar forced to 100% for the
  top opportunity).
- Gain itself is `simulated_alignment − current_alignment` after a small step
  (e.g. −0.5 pp body fat). Simulation only — not a forecast.
- Position vs Target and Alignment History unchanged in role; no radar charts.

## Manual import (`/manual_import/`)

- Phone-first step flow; **Close** in the header returns to the dashboard
  during entry and after save.
- Post-save still shows Target Alignment, Δ vs previous, sparkline, mini
  component bars, and primary opportunity.
- Trusted-device cookie keeps known phones signed in without retyping the
  password every time.

## Settings surface

- **Profile** — single editor for the signed-in user’s body profile.
- **Body Compass targets** — versioned ranges (DB only).
- **Compass algorithm** — optional soft/hard / weight prefs.
- **Trusted devices** — revoke one or all.

## Related docs

| Topic | Doc |
|-------|-----|
| Deploy, CLI, import, tests | [operations.md](operations.md) |
| Auth, cookies, exposure | [privacy.md](privacy.md) |
| Routes, modules, ER | [architecture.md](architecture.md) |
| Compass checklist | [features/body-compass-as-built.md](features/body-compass-as-built.md) |
| Original Compass product spec | [features/body-compass-spec.md](features/body-compass-spec.md) |
