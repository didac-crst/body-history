# Architecture

## Components

```mermaid
flowchart TB
  client["Browser / iPhone homescreen"]
  app["body-history<br/>Django + gunicorn<br/>host :3060 → container :8000"]
  db["PostgreSQL shared cluster<br/>DB body_history · schema body"]
  imports["Host data volume<br/>/srv/satellite/data/body-history/imports"]
  exports["Host data volume<br/>/srv/satellite/data/body-history/exports"]

  client --> app
  app --> db
  app -.-> imports
  app -.-> exports
```

## Request surfaces

```mermaid
flowchart LR
  login["/login/"] --> dash["/"]
  dash --> compass["/compass/"]
  dash --> manual["/manual_import/"]
  dash --> history["/history/"]
  dash --> chart["/chart/"]
  dash --> excel["/import/"]
  dash --> settings["/settings/"]
  history --> csv["/history/export.csv"]
  compass --> histApi["/api/compass-history/"]
  compass --> simApi["/api/compass-simulate/"]
  manual --> postSave["Post-save Compass + alignment delta"]
  settings --> devices["Trusted devices"]
```

## Important routes

| Path | Purpose |
|------|---------|
| `/` | Dashboard (latest metrics + Target Alignment + guidance) |
| `/compass/` | Body Compass detail (scores, history, position bars, impact, simulator) |
| `/api/compass-history/` | Alignment / component score series JSON |
| `/api/compass-simulate/` | Counterfactual score JSON |
| `/manual_import/` | Phone step-by-step entry + Close to dashboard + post-save Compass |
| `/history/` | Table + filters |
| `/history/export.csv` | CSV export with derived BMI / fat mass |
| `/chart/` | Metric trend chart (raw + smooth) |
| `/import/` | Excel dry-run / import UI |
| `/settings/` | Profile, targets, algorithm prefs, devices |
| `/login/` | Sign-in |

## Profile

Each authenticated Django user has exactly one `Profile` (`OneToOneField`).
All measurement / Compass / settings writes apply to that profile. Users cannot
see another user’s data.

## Manual import flow

```mermaid
flowchart LR
  close["Close → dashboard"] -.-> w
  w["1. Weight"] --> f["2. Fat %"]
  f --> m["3. Muscle %"]
  m --> d["4. Date"]
  d --> r["5. Review and save"]
  r --> c["Post-save Compass + Δ vs previous"]
  c --> dash["Close / View dashboard"]
```

## Body Compass modules

```mermaid
flowchart TB
  views["views / templates"] --> compass["compass.py"]
  views --> history["compass_history.py"]
  views --> charts["charts.py"]
  views --> preview["preview.py"]
  views --> profiles["profiles.py"]
  compass --> scoring["scoring.py"]
  compass --> trends["trends.py"]
  compass --> recs["recommendations.py"]
  compass --> guidance["guidance.py"]
  compass --> prefs["preferences.py"]
  history --> scoring
  history --> prefs
  charts --> history
  charts --> prefs
  compass --> db["ProfileTarget + CompassPreferences in DB"]
```

Personal **target destinations** live only in `ProfileTarget` rows.  
Algorithm defaults live in `scoring.AlgorithmConfig`; optional overrides in `CompassPreferences`.

### Decision charts (shipped)

| Chart | Implementation |
|-------|----------------|
| Alignment History | ECharts time series via `/api/compass-history/` + `static/js/compass.js` |
| Position vs Target | HTML/CSS range bars from `records/charts.position_vs_target` |
| Opportunity Impact | Absolute 0–100 track; segment from current → simulated alignment (`records/charts.opportunity_impact`) |
| Dashboard / mobile mini | SVG sparkline + compact score bars (`alignment_sparkline`, `component_mini_bars`) |

Radar/spider charts are intentionally not used.

## Domain model (summary)

```mermaid
erDiagram
  USER ||--|| PROFILE : owns
  USER ||--o{ TRUSTED_DEVICE : has
  PROFILE ||--o{ MEASUREMENT : has
  PROFILE ||--o{ PROFILE_TARGET : has
  PROFILE ||--o| COMPASS_PREFERENCES : has
  PROFILE ||--o{ IMPORT_BATCH : has
  IMPORT_BATCH ||--o{ MEASUREMENT_IMPORT_ROW : contains
  MEASUREMENT ||--o| MEASUREMENT_IMPORT_ROW : may_link

  USER {
    int id
    text username
  }
  PROFILE {
    uuid id
    text display_name
    numeric height_cm
    text timezone
  }
  MEASUREMENT {
    uuid id
    timestamptz measured_at
    numeric weight_kg
    numeric body_fat_percent
    numeric muscle_percent
    text source
  }
  PROFILE_TARGET {
    uuid id
    date valid_from
    date valid_to
    numeric weight_min_kg
    numeric weight_max_kg
    numeric body_fat_min_percent
    numeric body_fat_max_percent
    numeric muscle_min_percent
    numeric muscle_max_percent
  }
  COMPASS_PREFERENCES {
    uuid id
    numeric weight_importance
    numeric body_fat_importance
    numeric muscle_importance
    numeric fat_soft_pp
    numeric fat_hard_pp
  }
  IMPORT_BATCH {
    uuid id
    text file_hash
    int accepted_count
  }
  TRUSTED_DEVICE {
    uuid id
    text token_hash
    timestamptz expires_at
  }
```

Derived metrics (BMI, fat mass kg, deltas, Target Alignment) are computed in code, not stored as facts on each measurement row.

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
