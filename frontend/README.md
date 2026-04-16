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
```

## Structure

```text
src/api/          fetch client and API modules
src/hooks/        TanStack Query hooks and shared URL-param hooks
src/pages/        Dashboard, analytics, sync, scope, capacity, backlog, planning
src/components/   layout and shared UI components
src/types/        TypeScript interfaces mirrored from backend responses
src/utils/        formatters and constants
```
