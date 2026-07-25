# Body History — Project Decision

## Name

Use English naming for the application and database objects.

Chosen app name:

```text
body-history
```

Avoid `pes` as the durable app name. It is understandable personally, but it mixes Catalan with the rest of the satellite naming and is less clear in code, URLs, database names, backups, and future docs.

UI display name can be:

```text
Body History
```

Optional subtitle:

```text
Weight and body composition history
```

## Satellite Locations

Application project:

```text
/srv/satellite/apps/body-history
```

Raw/imported files, not committed to git:

```text
/srv/satellite/data/body-history/imports
```

Generated exports/reports, not committed to git:

```text
/srv/satellite/data/body-history/exports
```

Secrets:

```text
/srv/satellite/secrets/body-history.env
```

NAS backups are handled by the existing whole-cluster PostgreSQL backup plan, not by this app directly.

## Source Workbook

The original workbook should be preserved as immutable import evidence.

Place it here:

```text
/srv/satellite/data/body-history/imports/Pes.xlsx
```

Do not keep the workbook inside the app repository unless it is explicitly gitignored and only used as a local fixture. It contains personal health data.

## Database Choice

Use the existing PostgreSQL/TimescaleDB cluster, but create a separate logical database for this app.

Recommended database:

```text
body_history
```

Recommended application user:

```text
body_history_app
```

Recommended schema inside the database:

```text
body
```

Rationale:

- use the current Postgres infrastructure;
- keep personal health data separate from weather and forecast data;
- allow independent migrations and permissions;
- allow the whole-cluster backup job to cover it automatically.

Do not put these tables into the existing `weatherstation` database.

## TimescaleDB Guidance

Do not create hypertables for the MVP.

The dataset is tiny: hundreds of rows over decades. Even with daily measurements for years, normal PostgreSQL tables are enough.

Use plain tables with:

- `timestamptz` for `measured_at`;
- normal B-tree indexes;
- SQL views or backend functions for derived metrics.

TimescaleDB is installed in the cluster, but using Timescale features here would add complexity without value.

## Recommended Port

This is a private UI app, so use the `3xxx` UI range.

Recommended host port:

```text
3060
```

Rationale: slot `60` is documented as the future app group in the satellite port policy.

Expected public URL: your Cloudflare hostname for this app (configured in host secrets, not committed).

Local/LAN port remains:

```text
http://<lan-host>:3060/
```

## Proposed Stack

Preferred implementation:

- Django
- PostgreSQL
- server-rendered templates
- small JavaScript only where useful for charts/interactions
- ECharts or Plotly.js for charts
- Docker Compose
- pytest

Reasoning:

This app is mostly authenticated CRUD, forms, admin-style records, imports, validation, filters, and reports. Django fits that better than FastAPI for the MVP.

FastAPI is acceptable if future API integrations are the priority, but Django is the more pragmatic default for a private database-backed personal records app.

## Privacy Boundary

This app stores personal health data.

Requirements:

- require authentication even when accessed through Cloudflare Tunnel;
- do not rely on Cloudflare Tunnel alone as application authentication;
- support trusted-device sessions to avoid frequent password entry on known devices;
- expose externally only through Cloudflare Tunnel / Cloudflare Access or equivalent, never router port forwarding;
- do not commit workbook data to git;
- avoid verbose logs containing measurement values;
- include CSV export;
- rely on the whole-cluster NAS backup job for database backup.

Authentication should use Django sessions plus a trusted-device token stored in a secure HttpOnly cookie. Store only a hash server-side, expire tokens after 180 days by default, and provide revocation. Do not support passwords or login tokens in URLs.

## MVP Scope

Build first:

1. schema/migrations;
2. profile and target config;
3. dry-run Excel importer;
4. audited import batch records;
5. measurement create/edit/delete;
6. history table;
7. latest values dashboard;
8. primary trend chart;
9. CSV export;
10. import verification report.

Do not implement medical advice, calorie tracking, ML, native mobile app, or exact recreation of every Excel chart in the MVP.
