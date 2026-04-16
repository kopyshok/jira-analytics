# Jira Analytics Frontend

React SPA для локального сервиса Jira Analytics.

## Stack

- React 19
- TypeScript 6
- Vite 8
- Ant Design 6
- TanStack Query
- Recharts

## Setup

```bash
npm install
cp .env.example .env
npm run dev
```

Dev server: http://localhost:5173

Backend API URL задается через `VITE_API_BASE_URL`:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## Checks

```bash
npm run lint
npm run build
npm run e2e:install
npm run e2e
```

Full-stack smoke from the repository root:

```powershell
.\scripts\smoke-local.ps1
.\scripts\e2e-local.ps1
```

`npm run e2e` starts the backend on `127.0.0.1:8010` with an isolated
SQLite database at `data/e2e.db`, starts Vite on `127.0.0.1:5174`, then
checks the main SPA routes in Chromium. Jira credentials are not required.

## Structure

```text
src/api/          fetch client and API modules
e2e/             Playwright browser smoke for main product routes
src/hooks/        TanStack Query hooks and shared URL-param hooks
src/pages/        lazy-loaded Dashboard, analytics, sync, scope, capacity, backlog, planning
src/components/   layout and shared UI components
src/types/        TypeScript interfaces mirrored from backend responses
src/utils/        formatters and constants
```
