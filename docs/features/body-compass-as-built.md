# Body Compass — As Built

Status of the shipped Body Compass feature versus
[body-compass-spec.md](body-compass-spec.md).

**Status: complete for phases 1–6 and the spec acceptance criteria.**  
Optional later ideas are listed at the bottom; they are not blockers.

Personal target values live in the `body_history` database only. They are not
committed as code constants, migrations with fixed personal numbers, or fixtures.

## Shipped now

```mermaid
flowchart TB
  profile["User body profile"] --> settings["Settings: profile / targets / prefs"]
  settings --> db["ProfileTarget / CompassPreferences / Profile"]
  db --> service["records/compass.py"]
  service --> charts["records/charts.py"]
  service --> dash["Dashboard mini-charts"]
  service --> page["/compass/ decision charts"]
  service --> mobile["/manual_import/ post-save + mini-charts"]
  page --> historyApi["/api/compass-history/"]
  page --> simApi["/api/compass-simulate/"]
```

| Area | Status |
|------|--------|
| Target ranges on `ProfileTarget` | Done |
| One profile per UI user | Done |
| User-scoped profile for all views | Done |
| Component scores 0–100 + overall Target Alignment | Done |
| Confidence + freshness | Done |
| Direction vs prior comparable period | Done |
| What-changed attribution on `/compass/` | Done |
| Alignment History chart + component toggles | Done |
| Position vs Target range bars | Done |
| Opportunity Impact absolute 0–100 move bars | Done |
| Dashboard / mobile sparkline + component mini-bars | Done |
| Manual import Close → dashboard | Done |
| Overall score line emphasised on chart | Done |
| Default chart mode: today’s target | Done |
| Primary / secondary opportunity ranking | Done |
| Interactive opportunity simulator | Done |
| Milestone suggestions | Done |
| Action guidance copy | Done |
| Fitness signals (BMI / fat mass / target bands) | Done |
| Settings active-target preview + soft/hard bands | Done |
| Post-save alignment delta vs previous reading | Done |
| `CompassPreferences` + Settings UI | Done |
| Dashboard / Compass / mobile post-save | Done |
| `seed_compass_targets` CLI (args only) | Done |
| No radar/spider charts | Done (by design) |

## Compass charts (as built)

Matches the **Compass Charts** section of the spec:

1. **Alignment History** — overall + weight/fat/muscle over time; overall visually dominant; today’s-target mode default; historical mode available and labelled.
2. **Position vs Target** — horizontal range bars for trend vs ideal (soft band visible); gap labelled in kg or pp; aligned values marked clearly.
3. **Opportunity Impact** — absolute 0–100 alignment track; each row shows today → simulated and `+gain`; insufficient/maintain states without fake recommendations.
4. **Dashboard & mobile mini-charts** — sparkline + three component bars only; no full chart controls on post-save. Manual import header has **Close** → dashboard.

## Spec acceptance criteria

All items from the spec are met:

1. Versioned target ranges in DB  
2. Initial weight center via DB data (not code)  
3. Fat/muscle targets from sustained historical bests via DB data  
4. Overall Target Alignment 0–100  
5. Decomposable component scores  
6. Improving / stable / drifting direction  
7. What-changed attribution  
8. Primary + optional secondary opportunity  
9. Explanation of why  
10. Weight / fat / muscle simulation  
11. Alignment History, Position vs Target, and Opportunity Impact charts  
12. Maintain when near target  
13. Mobile post-save Compass overview (with mini charts)  
14. Composition preferred over blind weight loss  

## Delivery phases covered

1. Alignment foundation  
2. Direction + history chart  
3. Mobile post-save compass (+ delta + mini-charts)  
4. Recommendations + simulator  
5. Guidance + fitness signals + algorithm prefs  
6. One profile per user + target preview  
7. Spec decision charts (Position vs Target, Opportunity Impact, mini-charts)  

## Optional later (not required)

- Richer wearable / extra fitness signal inputs beyond derived BMI/fat mass  

## Runtime boundary reminder

| May live in code | Must live in DB / host data only |
|------------------|-----------------------------------|
| Default scoring weights / soft-hard bands | Weight / fat / muscle target ranges |
| Default trend windows | Active and historical `ProfileTarget` rows |
| | Optional per-profile `CompassPreferences` overrides |

## Key modules

| Module | Role |
|--------|------|
| `records/charts.py` | Position bars, impact bars, sparkline payloads |
| `records/profiles.py` | Resolve the signed-in user’s single profile |
| `records/scoring.py` | Range scoring + `AlgorithmConfig` defaults |
| `records/preferences.py` | Resolve profile algorithm overrides |
| `records/guidance.py` | Action guidance + fitness signals |
| `records/preview.py` | Settings target/trend preview |
| `records/compass.py` | Structured snapshot for UI |
| `records/compass_history.py` | Alignment history series + simulator payload |
| `static/js/compass.js` | History chart + simulator client |

## Operator notes

See [../operations.md](../operations.md#body-compass) for targets, prefs, and APIs.  
See [../evolutions.md](../evolutions.md) for ownership, auth, and UX decisions after the original specs.

Decision charts use range bars and ranked impact bars — not radar/spider charts.
