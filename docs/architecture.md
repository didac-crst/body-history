# Architecture

## Components

```text
Browser / iPhone homescreen
        │
        ▼
body-history (Django + gunicorn) :3060 → :8000
        │
        ▼
PostgreSQL (shared Timescale cluster) DB body_history / schema body
```

Raw files stay on the host data volume:

```text
/srv/satellite/data/body-history/imports
/srv/satellite/data/body-history/exports
```

## Important routes

| Path | Purpose |
|------|---------|
| `/` | Dashboard |
| `/manual_import/` | Phone step-by-step measurement entry |
| `/history/` | Table + filters |
| `/history/export.csv` | CSV export with derived BMI / fat mass |
| `/chart/` | Trend chart (raw points + smooth) |
| `/import/` | Excel dry-run / import UI |
| `/settings/` | Profile, targets, trusted devices |
| `/login/` | Sign-in |

## Domain model (summary)

- `profiles` — height, timezone, smoothing prefs
- `profile_targets` — versioned targets by date range
- `measurements` — weight / optional fat% / optional muscle%
- `import_batches` + `measurement_import_rows` — audited Excel import
- `trusted_devices` — hashed long-lived device tokens

Derived metrics (BMI, fat mass kg, deltas) are computed in code, not stored as facts on each row.

## Excel mapping

Source sheet: `General`

| Workbook | App field |
|----------|-----------|
| Data | `measured_at` |
| Pes | `weight_kg` |
| % Grassa | `body_fat_percent` (fraction → percent) |
| % Muscul | `muscle_percent` (fraction → percent) |
| Alçada | profile `height_cm` (metres → cm) |
| IMC / Grassa / scores | ignored formulas; recalculate or drop |

## Local development notes

Production runs entirely in Docker.  
Optional SQLite for tests via `BODY_HISTORY_USE_SQLITE=1`.
