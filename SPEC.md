# Body History — Cursor Implementation Specification

## Role of This Project

Build a small private database-backed web application to replace the existing `Pes.xlsx` spreadsheet as the source of truth for long-term weight and body-composition history.

This project must preserve the original measurements, make calculations reproducible, and provide useful trend views without embedding spreadsheet formulas into the data model.

Cursor should implement the app in this folder:

```text
/srv/satellite/apps/body-history
```

Raw workbook/import data belongs outside the app repository:

```text
/srv/satellite/data/body-history/imports/Pes.xlsx
```

Do not commit personal measurement data to git.

---

## Naming

Use English names throughout code, database, URLs, docs, and UI.

Chosen durable app name:

```text
body-history
```

UI name:

```text
Body History
```

Do not name the app `pes`. The source workbook may remain named `Pes.xlsx`, but the product and schema should be English.

Recommended database:

```text
body_history
```

Recommended database user:

```text
body_history_app
```

Recommended schema:

```text
body
```

Recommended host port:

```text
3060
```

---

## Architecture Decision

Use the existing PostgreSQL/TimescaleDB cluster, but create a separate database for this app.

Do not store body-history tables in the `weatherstation` database.

Do not use Timescale hypertables for the MVP. This is a very small, sparse dataset. Plain PostgreSQL tables are simpler and more appropriate. The app still uses the existing TimescaleDB PostgreSQL instance; it just does not need Timescale-specific hypertable features.

Recommended stack:

- Django
- PostgreSQL
- Django migrations
- server-rendered templates
- small progressive JavaScript where useful
- ECharts or Plotly.js for charts
- Docker Compose
- pytest

Rationale:

This application is mostly authenticated CRUD, forms, imports, validation, tables, charts, and admin-like workflows. Django is the pragmatic default for this shape of application.

FastAPI is acceptable only if there is a strong reason to prioritize external API integrations over form/database productivity.

---

## Privacy Requirements

This app stores personal health data.

Requirements:

- require authentication even when accessed through Cloudflare Tunnel;
- do not rely on Cloudflare Tunnel alone as application authentication;
- support trusted-device sessions to avoid frequent password entry on known devices;
- do not log measurement values unnecessarily;
- do not commit raw workbook or exported health data;
- keep secrets in `/srv/satellite/secrets/body-history.env`;
- rely on the whole-cluster PostgreSQL NAS backup job for database backup;
- provide CSV export so the user is not locked into the app.

---

## Authentication and Exposure

The app is expected to be reachable through a Cloudflare Tunnel hostname. There should be no router port forwarding to the Raspberry Pi.

Cloudflare Tunnel is transport/exposure control, not sufficient application authentication by itself. The app must still require authentication.

Use Django's built-in authentication and session system as the primary mechanism.

Add trusted-device support for convenience:

1. First access requires normal username/password login.
2. Login form offers `Trust this device`.
3. If enabled, issue a long-lived random device token in a secure, HttpOnly cookie.
4. Store only a hash of the token server-side.
5. Store token metadata: profile/user, created_at, last_seen_at, expires_at, user_agent, optional label.
6. Default expiry: 180 days.
7. User can revoke trusted devices from settings.
8. Password change or explicit logout-all should invalidate trusted-device tokens.

Explicitly forbidden:

- passwords in URLs;
- login tokens in query strings;
- bearer tokens in bookmarks;
- unauthenticated access just because the app is behind Cloudflare Tunnel.

Recommended cookie settings:

```text
HttpOnly = true
SameSite = Lax
Secure = true when served through HTTPS/Cloudflare
```

If Cloudflare Access is also configured later, keep Django auth initially. Any future trusted-proxy authentication should be designed explicitly and documented before removing Django login.

---

## Data Model

### profiles

Even if there is initially one profile, keep a profile entity.

```text
id                  uuid primary key
display_name        text not null
height_cm           numeric(5,2) not null
timezone            text not null
weight_unit         text not null default kg
created_at          timestamptz not null
updated_at          timestamptz not null
```

### measurements

```text
id                  uuid primary key
profile_id          uuid not null references profiles(id)
measured_at         timestamptz not null
weight_kg           numeric(5,2) not null
body_fat_percent    numeric(5,2)
muscle_percent      numeric(5,2)
source              text not null
notes               text
conditions          text
is_excluded         boolean not null default false
exclusion_reason    text
legacy_payload      jsonb
created_at          timestamptz not null
updated_at          timestamptz not null
```

Constraints:

```text
weight_kg > 0
body_fat_percent is null or between 0 and 100
muscle_percent is null or between 0 and 100
```

Do not impose narrow hard constraints like 40-200 kg. Use warnings for improbable values instead.

Allow multiple measurements per day. Warn, but do not reject, when another measurement already exists on the same local date.

### profile_targets

Targets must be versioned.

```text
id                          uuid primary key
profile_id                  uuid not null references profiles(id)
valid_from                  date not null
valid_to                    date
target_weight_kg            numeric(5,2)
target_bmi                  numeric(5,2)
target_body_fat_percent     numeric(5,2)
target_muscle_percent       numeric(5,2)
created_at                  timestamptz not null
updated_at                  timestamptz not null
```

Initial imported configuration may use:

```text
target_bmi = 22
target_body_fat_percent = 17
target_muscle_percent = 39.8
height_cm = 181
```

Do not hard-code these values in calculations.

### import_batches

```text
id                  uuid primary key
profile_id          uuid not null references profiles(id)
filename            text not null
file_hash           text not null
imported_at         timestamptz not null
row_count           integer not null
accepted_count      integer not null
rejected_count      integer not null
metadata            jsonb not null default {}
```

### measurement_import_rows

Keep row-level auditability for the Excel migration.

```text
id                  uuid primary key
import_batch_id     uuid not null references import_batches(id)
source_sheet        text
source_row          integer
raw_payload         jsonb not null
measurement_id      uuid references measurements(id)
status              text not null
error_message       text
created_at          timestamptz not null
```

---

## Derived Metrics

Do not store these redundantly in `measurements`:

- BMI
- fat mass kg
- year
- ideal weight
- scores
- outlier score

Calculate them through backend domain functions, query annotations, or SQL views.

Definitions:

```text
bmi = weight_kg / (height_cm / 100)^2
fat_mass_kg = weight_kg * body_fat_percent / 100
```

If adding a SQL view, name it:

```text
body.measurement_metrics
```

---

## Excel Import

Implement import in two phases.

### Phase 1: Dry Run

The dry run must read the workbook and produce a report without writing measurements.

Report:

- detected sheets;
- candidate measurement count;
- date range;
- missing values;
- invalid values;
- duplicate local dates;
- formulas ignored;
- column mappings;
- source file hash;
- expected versus parsed statistics.

Expected source workbook characteristics from prior analysis:

```text
691 unique measurement dates
first date: 2005-04-15
last date: 2025-11-15
weight range: 70.0-82.8 kg
body-fat values start around 2007-09
muscle values start around 2015-04
```

Do not assume these numbers blindly. Validate them against the actual file.

### Phase 2: Import

The import should:

- create an `import_batches` row;
- create `measurement_import_rows` for each source row;
- insert accepted measurements;
- preserve rejected rows with error messages;
- never silently overwrite existing measurements;
- support an idempotency guard using file hash and source row identity.

Mapping guidance:

```text
Data        -> measured_at
Pes         -> weight_kg
% Grassa    -> body_fat_percent
% Muscul    -> muscle_percent
Alçada      -> profile.height_cm, not per measurement
IMC         -> recalculate, do not import as fact
Grassa      -> recalculate, do not import as fact
Scores      -> do not import as facts
Outlier     -> optionally preserve in legacy_payload only
```

Important conversion:

If Excel stores body composition as fractions such as `0.203`, store and display `20.3`, not `0.203`.

---

## UI Scope

### Main Dashboard

Answer:

1. latest state;
2. recent direction;
3. whether change is meaningful or noise;
4. comparison with long-term history.

Top values:

- latest weight;
- latest BMI;
- latest body-fat percentage;
- estimated fat mass;
- latest muscle percentage;
- days since last measurement;
- 7-day, 30-day, 90-day, and 1-year changes.

Deltas should use rolling/trend comparison where possible, not a naive nearest isolated row only.

### Measurement Entry

Fast form:

- date/time defaults to now;
- weight required;
- body fat optional;
- muscle optional;
- source default `manual`;
- notes optional;
- conditions optional.

Actions:

- save;
- save and add another;
- edit;
- delete with confirmation.

### History Table

Columns:

```text
Date | Weight | BMI | Fat % | Fat kg | Muscle % | Source | Notes
```

Features:

- sort;
- filter;
- edit;
- export CSV;
- show missing composition values;
- show excluded records;
- show imported/manual source.

### Charts

MVP chart:

- one primary timeline;
- metric selector: weight, BMI, fat %, fat mass, muscle %;
- ranges: 30 days, 90 days, 1 year, 5 years, all time;
- raw points plus smoothed trend;
- optional target line.

Do not make a visually dominant line connecting every isolated raw measurement by default. Raw points plus smoothing is more honest.

### Configuration

Profile:

- display name;
- height;
- timezone;
- date format;
- units.

Targets:

- target weight;
- target BMI;
- target body-fat percentage;
- target muscle percentage;
- optional target ranges later.

Analysis:

- smoothing method/window;
- outlier strategy;
- included/excluded records in summaries.

---

## Outliers and Warnings

Separate validation warnings from analytical exclusions.

Validation warnings detect likely entry mistakes:

- future date;
- body fat entered as `0.203` instead of `20.3`;
- duplicate same-day measurement;
- unusually large change since previous measurement;
- values far outside personal history.

Analytical exclusion is manual and stored as:

```text
is_excluded
exclusion_reason
```

Do not automatically delete or mutate suspicious measurements.

Avoid global mean +/- 2 standard deviations as the only method. It is weak for a 20-year history where valid life-period shifts can occur.

---

## Docker / Deployment

Use Docker Compose in the app folder.

Recommended service:

```text
body-history
```

Recommended container:

```text
body-history
```

Host port:

```text
3060:8000
```

Use the shared database over the existing Postgres host/port and credentials in:

```text
/srv/satellite/secrets/body-history.env
```

Do not expose the database directly from this project.

---

## Tests

Required tests:

- BMI calculation;
- fat mass calculation;
- percent fraction conversion from Excel;
- duplicate date warning;
- multiple measurements on same day allowed;
- target version lookup by date;
- import dry-run count/date-range validation;
- importer does not import formulas as facts;
- invalid rows are recorded, not silently dropped;
- excluded measurements are omitted from default trend summaries;
- CSV export includes derived metrics.

---

## Acceptance Criteria

MVP is complete when:

1. app is reachable on the configured public hostname and LAN port `3060`;
2. authentication is required;
3. database and migrations are isolated in `body_history` / `body`;
4. Excel dry-run produces a reconciliation report;
5. Excel import is auditable and idempotent;
6. measurements can be created, edited, deleted, filtered, and exported;
7. dashboard shows latest values and basic trend deltas;
8. primary chart shows raw points and smoothed trend;
9. profile height and targets are configurable/versioned;
10. no raw health workbook or exports are committed to git;
11. tests cover calculations, import behaviour, duplicates, and target versioning.

---

## Explicit Non-Goals

Do not implement in MVP:

- medical diagnosis;
- calorie tracking;
- native mobile app;
- SPA frontend;
- ML;
- Timescale hypertables;
- every historical Excel chart;
- public internet exposure;
- storing every derived formula result as a fact.
