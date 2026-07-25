# Body History — Body Compass Feature Specification

Product/feature brief for Body Compass.

For what is already shipped, see [body-compass-as-built.md](body-compass-as-built.md).

## Purpose

Body History should not only record measurements. It should help answer:

```text
What is the most useful direction for me to move next?
```

This feature is a personal fitness compass, not a medical diagnosis system.

It evaluates body-composition direction against user-defined target ranges and explains the result in decomposable, auditable terms.

## Naming Decision

Keep the application name:

```text
body-history
```

Name this feature:

```text
Body Compass
```

Reason: the app is the long-term record, importer, table, charts, exports, settings, and future data store. The compass is one major feature inside it.

UI labels may use:

```text
Compass
Target Alignment
Primary Opportunity
```

Avoid:

```text
Health Score
Fitness Score
Medical Status
```

## Product Principles

1. Optimise body composition, not weight alone.
2. Reward sustainable trends rather than single readings.
3. Explain every score.
4. Use target ranges, not hard-coded ideal values.
5. Preserve historical target versions.
6. Never encourage weight loss when it worsens body composition.
7. Always allow `Maintain` as a valid recommendation.

Examples:

- Weight down, fat up, muscle down: negative.
- Weight up, fat stable/down, muscle up: potentially positive.
- Weight stable, fat down, muscle up: strongly positive.

## Runtime Data Boundary

Target values are personal runtime data. They must live in the `body_history` database, not in git, code constants, migrations, committed fixtures, or static JSON files.

Code may define defaults for algorithm behaviour, such as scoring weights and trend windows. Code must not embed the user's personal target values as durable constants.

The app should let the user create or edit the active target profile from the settings UI. A one-off management command is acceptable for initial setup only if it writes rows into the database and does not commit the values to source control.

The source workbook and derived personal target proposals are also personal data. They should stay outside git, under:

```text
/srv/satellite/data/body-history/imports
```

## Current Implementation Context

The current model has `ProfileTarget` with single-value target fields:

```text
target_weight_kg
target_bmi
target_body_fat_percent
target_muscle_percent
```

Body Compass requires target ranges. Cursor should migrate the target model rather than treating the existing single-value targets as sufficient.

## Initial Target Guidance

The user wants an ideal weight centered around:

```text
72.5 kg
```

This value should be inserted as database data for the user's active `ProfileTarget`, not hard-coded into the application.

Recommended initial weight target range to store in DB:

```text
72.0-73.0 kg
```

or, if the user prefers a slightly less strict target:

```text
72.0-73.5 kg
```

Body-fat and muscle targets should be derived from the user's best sustained historical values, not arbitrary generic values and not one exceptional scale reading.

Workbook analysis found:

```text
Lowest single body-fat reading: about 13.6%
Best sustained 90-day low-fat period: about 14.9-15.1% average
Highest single muscle reading: about 39.8%
Best sustained 90-day high-muscle period: about 38.2-38.3% average
```

Recommended initial target proposals to store in DB after user confirmation:

```text
Weight:   72.0-73.0 kg, centered around 72.5 kg
Body fat: 15.0-16.5%, derived from sustained historical low-fat periods
Muscle:   38.0-39.0%, derived from sustained historical high-muscle periods
```

These are not code defaults. They are user-specific profile target data.

Do not set body-fat target to the single historical minimum unless the user explicitly chooses it. A single low consumer-scale reading may be noise.

## Data Model Changes

### ProfileTarget

Extend or migrate `ProfileTarget` to target ranges:

```python
class ProfileTarget(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    weight_min_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weight_max_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    body_fat_min_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    body_fat_max_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    muscle_min_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    muscle_max_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
```

Validation:

- min must be <= max;
- target versions must not overlap for the same profile;
- at least one target dimension must be configured;
- BMI remains derived from weight and height;
- old single-value targets should migrate into narrow ranges or be retained only as legacy fields during migration.

### CompassPreferences

Optional in v1, defaults may be constants first:

```python
class CompassPreferences(models.Model):
    profile = models.OneToOneField(Profile, on_delete=models.CASCADE)
    weight_importance = models.DecimalField(default=Decimal("0.25"))
    body_fat_importance = models.DecimalField(default=Decimal("0.45"))
    muscle_importance = models.DecimalField(default=Decimal("0.30"))
    trend_window_days = models.PositiveIntegerField(default=30)
    comparison_window_days = models.PositiveIntegerField(default=30)
```

These algorithm preferences are not personal target values. They may be app defaults or DB-backed preferences.

## Scoring

Use range-based component scores from 0 to 100.

Metrics:

- weight;
- body fat;
- muscle.

Inside target range:

```text
score = 100
```

Outside target range:

- ideal to soft boundary: linearly decrease from 100 to 70;
- soft to hard boundary: linearly decrease from 70 to 0;
- beyond hard boundary: 0.

Scoring function must support asymmetric lower/upper tolerance:

```python
score_against_range(value, ideal_min, ideal_max, lower_soft, lower_hard, upper_soft, upper_hard)
```

Missing component values must not be scored as zero. Calculate overall alignment from available components only and reduce confidence.

Default algorithm weights:

```text
Weight:   25%
Body fat: 45%
Muscle:   30%
```

## Confidence

Expose confidence separately from score.

Confidence depends on:

- number of recent measurements;
- recency of latest measurement;
- body-fat availability;
- muscle availability;
- variability of recent readings;
- consistency of measurement conditions if available.

States:

```text
High
Medium
Low
Insufficient data
```

Freshness defaults:

```text
latest <= 14 days: fresh
15-30 days: ageing
> 30 days: stale
```

## Direction

Direction compares current smoothed alignment against a previous comparable period.

Default periods:

```text
7 days
30 days
90 days
```

Thresholds:

```text
change > +2: Improving
-2 <= change <= +2: Stable
change < -2: Drifting away
```

Also compute component direction.

## Recommendation Engine

Recommendation categories:

```text
REDUCE_BODY_FAT
BUILD_MUSCLE
REDUCE_WEIGHT
GAIN_WEIGHT
MAINTAIN
IMPROVE_MEASUREMENT_CONSISTENCY
INSUFFICIENT_DATA
```

Use counterfactual simulation with small realistic steps:

```text
Weight: +/- 0.5 kg
Body fat: +/- 0.5 percentage points
Muscle: +/- 0.5 percentage points
```

For each simulation:

1. Recalculate component scores.
2. Recalculate overall alignment.
3. Measure potential gain.
4. Rank opportunities by alignment gain.
5. Reject internally inconsistent or undesirable scenarios.

Do not call this the fastest improvement. Use:

```text
greatest alignment impact
```

Protect muscle:

- if weight is high but fat is acceptable and muscle is high, do not recommend weight loss just to hit weight;
- if weight is high, fat high, and muscle low, recommend reducing fat while preserving/building muscle;
- if weight is normal, fat high, and muscle low, recommend recomposition;
- if all metrics are inside range, recommend maintain.

## Domain Module Structure

Create dedicated modules:

```text
records/
  metrics.py
  trends.py
  scoring.py
  compass.py
  recommendations.py
```

Business logic must return structured data, not final HTML strings.

## Dashboard UI

Add a compact main dashboard card:

```text
TARGET ALIGNMENT
84 / 100
Improving
+6 over 30 days
Medium confidence
```

Component breakdown:

```text
Weight     94 / 100  Stable
Body fat   76 / 100  Improving
Muscle     83 / 100  Slight decline
```

Primary opportunity card:

```text
PRIMARY OPPORTUNITY
Reduce body fat while preserving muscle.
This would currently improve alignment more than losing weight alone.
```

## Mobile Post-Save Flow

The mobile measurement entry flow should not simply save and return to history.

After saving a new measurement, show a compact post-save overview that answers:

1. What changed with this new value?
2. Did the compass alignment move?
3. Which component is now most important?
4. Is the result noisy/low-confidence?

Required post-save panel:

```text
Saved
75.2 kg · 20.3% fat · 35.3% muscle

Target Alignment
84 / 100   +1 since previous trend
Medium confidence

Primary opportunity
Reduce body fat while preserving muscle.

Latest vs trend
Latest: 75.2 kg
30-day trend: 75.6 kg
```

Rules:

- if only weight was entered, show weight impact but avoid body-composition recommendations;
- if composition values are missing, recommend consistency rather than fat/muscle direction;
- if this is a single isolated measurement, say trend guidance needs more data;
- provide buttons: `Add another`, `View dashboard`, `Edit measurement`;
- keep the panel mobile-first and readable in one screen where possible.

This post-save overview should reuse the same structured compass service as the main dashboard. Do not duplicate scoring logic in the view.

## Detailed Compass Page

Route:

```text
/compass/
```

Include:

- position versus destination table;
- alignment history chart;
- component history chart or toggles;
- what changed attribution;
- opportunity simulator.

Historical alignment should use the target version active at that date by default.

Optional mode:

```text
Recalculate all history using today's target
```

This must be explicitly labelled.

## Settings UI

Add a Body Compass section under settings.

Target form:

```text
Valid from
Weight min/max
Body fat min/max
Muscle min/max
```

Show derived info:

```text
Equivalent BMI range
Fat mass at target weight and body-fat range
```

Show target preview using current trend.

Show target history. Historically active target versions should not be destructively edited; create a new version instead.

## Safeguards

- no diagnosis;
- no `healthy/unhealthy` labels;
- no score above 100;
- no endless optimisation after target is reached;
- no single-reading strategic recommendation;
- consumer scale body-fat and muscle values must be described as estimates best used as trends.

## Tests

Required unit tests:

- inside-range score;
- upper and lower deviations;
- asymmetric tolerances;
- missing metrics;
- all metrics missing;
- target version selection;
- stable direction;
- improving direction;
- declining direction;
- counterfactual ranking;
- weight loss that worsens body composition;
- muscle gain that increases weight;
- score cap at 100;
- post-save view with full data;
- post-save view with weight only;
- post-save view with insufficient trend data;
- personal target values are loaded from DB, not code constants.

## Delivery Phases

### Phase 1 — Alignment Foundation

- target ranges;
- component scores;
- overall alignment;
- confidence;
- dashboard card;
- settings form;
- unit tests.

### Phase 2 — Direction

- trend calculation;
- comparison periods;
- improving/stable/declining states;
- component attribution;
- alignment history chart.

### Phase 3 — Mobile Post-Save Compass

- post-save overview after measurement creation;
- alignment delta from the new value;
- primary opportunity summary;
- insufficient-data handling;
- mobile-first layout.

### Phase 4 — Recommendations

- counterfactual simulator;
- ranked opportunities;
- conflict rules;
- primary/secondary directions;
- milestone generation.

### Phase 5 — Guidance and Simulation

- general action guidance;
- interactive simulator;
- richer explanations;
- optional extra fitness signals.

## Acceptance Criteria

The feature is complete when the user can:

1. Define versioned target ranges stored in the DB.
2. Use 72.5 kg as the initial weight target center via DB data, not code.
3. Base initial fat/muscle targets on sustained historical bests, stored as profile target data.
4. See current overall Target Alignment from 0 to 100.
5. Understand every component of the score.
6. See improving/stable/declining direction.
7. Understand which metric caused the change.
8. Receive one primary direction and optional secondary direction.
9. See why the direction was chosen.
10. Simulate changes to weight, fat and muscle.
11. Get a Maintain recommendation when target is reached.
12. After saving a mobile measurement, immediately see a compact compass overview.
13. Use the feature without being encouraged to optimise weight at the expense of body composition.
