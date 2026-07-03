## 1. Backend
- [x] 1.1 Add `completed_after` / `completed_before` `DateFilter`s (on `completed_date`, `date__gte` /
      `date__lte`) to `TaskFilterSet` and list them in `Meta.fields`.
- [x] 1.2 Tests: `completed_after`, `completed_before`, and both combined scope the stats payload.

## 2. Frontend
- [x] 2.1 Extend `TaskFilters` with `completed_after` / `completed_before` and serialise them in
      `getQueryString()` and `getQueryParams()`.
- [x] 2.2 Add a period selector to the stats page: Today / Last week / Last month / All time presets
      plus a custom From–To range, stored in the URL as `completed_after`/`completed_before`.
- [x] 2.3 Reflect the active preset (highlight, or "custom range" when the range matches no preset),
      and adapt the totals tiles for a bounded period ("completed in period").

## 3. Validation
- [x] 3.1 `uv run python manage.py test` and `uv run ruff check .`.
- [x] 3.2 `cd frontend && npm run build` succeeds.
