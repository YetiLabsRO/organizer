## ADDED Requirements

### Requirement: Statistics period range
The system SHALL accept `completed_after` and `completed_before` date parameters on
`GET /api/task/stats/` that bound the aggregated tasks to those whose completion date falls within
the inclusive window (compared on the local date of `completed_date`). The bounds MAY be used
independently or together, and their absence SHALL mean all-time (no completion-date bound).

#### Scenario: Lower bound scopes the payload
- **WHEN** an authenticated user requests `GET /api/task/stats/?completed_after=2026-01-10`
- **THEN** only tasks completed on or after 2026-01-10 contribute to every statistics section

#### Scenario: Upper bound scopes the payload
- **WHEN** an authenticated user requests `GET /api/task/stats/?completed_before=2026-01-10`
- **THEN** only tasks completed on or before 2026-01-10 contribute to the statistics

#### Scenario: Bounds combine into a window
- **WHEN** an authenticated user requests `GET /api/task/stats/?completed_after=2026-01-05&completed_before=2026-01-06`
- **THEN** only tasks completed within that inclusive two-day window contribute to the statistics
