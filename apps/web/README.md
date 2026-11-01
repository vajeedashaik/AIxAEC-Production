# apps/web (Next.js 16, :3000)

Landing, auth, dashboard, projects, upload and the floor-plan workspace. Talks only to `services/api`.
Owners: **P5** (shell, design system, `package.json`) and **P6** (`src/features/{viewer,workspace}`, the workspace route, `src/app/(dev)`). Frozen (P0/P7): `src/contracts`, `src/lib/api`, `src/mocks`. See `phases/shared/OWNERSHIP.md`.

## Run
```powershell
cd apps/web
npm install
copy .env.example .env.local      # set NEXT_PUBLIC_API_MOCKING=on to work without the backend
npm run dev                       # P6 uses: npm run dev -- --port 3001
```
- **Mock mode** (`NEXT_PUBLIC_API_MOCKING=on`): MSW serves every endpoint from `src/mocks` (fixtures from `packages/contracts`). Commands return PREVIEW/APPLIED with real version numbers, undo/redo work in memory, and uploads process through 8 stages in about 6 s. In development, mock mode also skips the Clerk route guard.
- **Clerk**: without keys in development the app runs unauthenticated. For the sign-in UI run `npx clerk@latest init --accountless` (temporary keys) or paste keys into `.env.local`. Production requires keys.

## Check
```powershell
npm run lint; npx tsc --noEmit; npm test; npm run build
npm run gen:contracts:check       # generated types and mock fixtures match packages/contracts
```

## Key pieces
- `DESIGN.md`: the design system (law). Tokens in `src/app/globals.css`.
- `src/contracts`: generated contract types (`npm run gen:contracts`, never edit by hand) + friendly names in `index.ts`.
- `src/lib/api`: typed client for every endpoint (`createApiClient`, `useApi`, `queryKeys`, `QueryProvider`, `ApiError`).
- `src/proxy.ts`: Clerk route guard for `/dashboard`, `/projects`, `/settings` (Next 16 renamed middleware to proxy).
