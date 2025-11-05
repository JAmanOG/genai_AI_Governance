# Frontend — Governance Dashboard (Reference)

This README documents the frontend portion of the Governance Dashboard. The frontend in this repository is provided for reference: production builds are expected to be served from a static site host or Next.js hosting platform (Cloud Run, Vercel, Firebase Hosting, etc.).

Use the Links section at the end to add your environment-specific URLs (production, staging, preview deployments, API endpoints, dashboards).

## Quick summary

- Framework: Next.js (App Router)
- Languages: TypeScript + React
- Styling: global CSS and Tailwind/postcss configuration (see `postcss.config.mjs`)
- Entrypoint: `app/page.tsx` (server/client rendering via the Next app directory)

This frontend is intended to consume the backend API gateway and GCS/Firestore-produced JSON artifacts. It is included primarily as a reference UI for the backend outputs.

## Repository layout (key files/folders)

- `app/` — Next.js App Router source (routes, API routes, top-level layout and pages):
  - `app/page.tsx` — main dashboard view
  - `app/layout.tsx` — global app layout (header, sidebar)
  - `app/api/` — serverless API routes used by the frontend (AI helpers, enriched dashboard endpoints)

- `components/` — React components used by pages (dashboard widgets, header, heatmap, KPI ribbon)

- `lib/` — shared helpers & hooks:
  - `app-data.ts` — types and data shapes used by the app
  - `use-app-data.ts`, `derived.ts` — domain-specific hooks and derived state

- `public/` — static assets served at root
- `styles/` — global CSS files (`globals.css`)
- `types/` — TypeScript definitions (e.g., `css.d.ts` for imported CSS modules)
- `.next/` — build output (ignored in source control but present in this workspace)

## Development (local)

The recommended local dev flow uses the Next.js dev server. On Windows PowerShell:

```powershell
cd d:\Dashboard\frontend
pnpm install            # or npm install / yarn install depending on your environment
pnpm dev                # starts Next.js dev server (usually on http://localhost:3000)
```

Notes:
- If you don't use pnpm, run `npm install` and `npm run dev` (package.json scripts present).
- The app may call an internal API route that proxies backend endpoints. Ensure the backend API gateway URL is configured in env or `lib/utils.ts` if you want to call a live backend.

## Environment variables (for local development)

Create a `.env.local` in `frontend/` or set env vars in your shell. Typical variables used by the frontend:

- NEXT_PUBLIC_API_GATEWAY_URL — URL of the backend API gateway (e.g., Cloud Function / Cloud Run URL)
- NEXT_PUBLIC_FEATURE_FLAG_* — feature flags used to toggle UI features
- NEXT_PUBLIC_SENTRY_DSN — optional Sentry DSN for error reporting

Add any other keys required by components under `app/api/` or the AI helper routes.

## Build & production

To create a production build:

```powershell
cd d:\Dashboard\frontend
pnpm build
pnpm start          # or deploy the `.next` output to your hosting target
```

Deployment targets (examples):
- Vercel — recommended for Next.js projects using App Router
- Cloud Run / Cloud Build — containerize and deploy for self-managed hosting
- Firebase Hosting + Cloud Functions — for static hosting + backend proxying

When deploying, set the public runtime env vars (NEXT_PUBLIC_*) via your hosting platform.

## Testing & linting

- TypeScript types and compile errors will surface in the editor and in CI. Run `pnpm build` to validate.
- Add unit tests (Jest/Testing Library) if you want to assert component behavior; this repo currently focuses on integration with the backend and does not include a test harness by default.

## Accessibility & performance

- Keep components semantic and screen-reader friendly (use ARIA attributes where necessary).
- Audit Lighthouse reports for the production build to identify perf regressions; prefer server-side rendering for initial load of KPI content.

## How the frontend consumes backend data

- Primary data source: API gateway (Cloud Function) that returns assembled JSON payload (kpis, districtRisks, alerts, departments)
- Secondary sources: static JSON files in GCS or Cloud Storage buckets (for bulk metrics or fallback)
- AI features: the app contains an `app/api/ai/` route — these server-side routes may proxy calls to LLMs or your backend AI wrappers. Configure API keys in hosting envs.

## Troubleshooting

- Blank dashboard / missing data: verify `NEXT_PUBLIC_API_GATEWAY_URL` is set and the gateway returns data. Check browser devtools network tab for failing requests.
- CORS issues: ensure backend allows requests from your frontend origin or proxy via server-side Next.js API routes.
- Type errors: run `pnpm build` to surface TypeScript errors and fix failing component props.

## Contributing

- Follow the project's TypeScript and formatting conventions.
- When adding features that depend on backend changes, coordinate with the backend owner so API shapes remain compatible.

---

If you want, I can also:
- add a small `README` page inside `app/` that the site can render for operators,
- generate a minimal GitHub Actions workflow to build and deploy the frontend to Vercel or Cloud Run,
- or add a tiny test harness (Jest + React Testing Library) with 1-2 smoke tests.

Update the placeholder links above with your deployment-specific URLs before sharing the README with external users.
