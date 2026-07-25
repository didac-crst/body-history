# Documentation

Diagrams in these docs use **Mermaid** only (no ASCII boxes).

| Doc | Purpose |
|-----|---------|
| [evolutions.md](evolutions.md) | **Later decisions** — ownership, auth/CSRF, CLI, Compass impact UX, manual import |
| [operations.md](operations.md) | Deploy, secrets, UI-user CLI, import, tests, profile, Compass |
| [privacy.md](privacy.md) | Auth, trusted devices, one-profile-per-user, cookies/CSRF, git hygiene |
| [architecture.md](architecture.md) | Stack, routes, Compass modules, data model |
| [features/body-compass-as-built.md](features/body-compass-as-built.md) | **Current** Body Compass status (source of truth for “done”) |
| [features/body-compass-spec.md](features/body-compass-spec.md) | Original Body Compass product/feature specification |

Upstream product decisions:

- [`../PROJECT_DECISION.md`](../PROJECT_DECISION.md) — naming, ports, database choice
- [`../SPEC.md`](../SPEC.md) — original MVP implementation specification

## Feature completeness

Body Compass phases 1–6 and the spec acceptance criteria are implemented,
including the **Compass Charts** set (Alignment History, Position vs Target,
Opportunity Impact, and dashboard/mobile mini-charts).

Ownership is **one profile per UI user**. See [evolutions.md](evolutions.md) for
auth, CLI, and UX refinements made after the original specs.

See [features/body-compass-as-built.md](features/body-compass-as-built.md) for the checklist and optional later ideas.
