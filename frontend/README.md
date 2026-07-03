# Organizer Frontend

Angular single-page app for the Organizer task & project manager. Consumes the Django REST API in
the repository root.

## Development

```bash
npm install
npm start            # dev server at http://localhost:4200
```

The backend must be running (see the repo root `CLAUDE.md`) and allow the dev origin via
`CORS_ALLOWED_ORIGINS`. The API base URL is configured in `src/environments/environment.ts`.

## Build & test

```bash
npm run build        # production build → dist/organizer-frontend
npm test             # unit tests
```

This app was migrated in-tree from the now-deprecated `organizer-ui` repository.
See `frontend/CLAUDE.md` for conventions.
