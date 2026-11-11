# OpenSesame frontend

React + TypeScript + Vite + Tailwind CSS mobile web app, implemented from Figma frames `3:22`–`3:25` in `UPnaTDKkcWdB8aktu4Oz8w`.

## Run (PowerShell)

```powershell
# Repository root: start the existing backend in demo mode
$env:OPENSESAME_OCR='mock'
$env:OPENSESAME_CLASSIFIER='mock'
.\.venv\Scripts\python.exe -m uvicorn src.app.main:app --host 127.0.0.1 --port 8000

# Separate terminal
cd frontend
npm.cmd ci
Copy-Item .env.example .env
npm.cmd run dev
```

Open http://localhost:5173. Node 22 is used for verification. Install backend dependencies first with `python -m venv .venv` and `.\.venv\Scripts\python.exe -X utf8 -m pip install -r requirements.txt` from the root. `-X utf8` avoids the Windows Korean code page issue in pip.

`VITE_API_BASE_URL` defaults to `http://localhost:8000`; restart Vite after changing it. A phone needs a reachable backend address instead of localhost, a permitted CORS origin and a suitable HTTPS deployment. Camera behavior depends on device/browser; desktop file pickers do not verify physical camera capture. Production hosting must serve index.html for client routes.

## Data and privacy

Only one multipart field, `file`, is sent to the existing `POST /analyze` endpoint. Allergies are compared locally and are never sent or logged. `utils/profileStorage.ts` temporarily uses sessionStorage pending a team decision; this is not a finalized persistence policy. When storage is blocked the current React state remains usable. Photos and analysis stay in memory, and object URLs are revoked. A results-page reload asks for a new scan.

`types/analysis.ts` preserves backend allergen IDs and verdict enums. `utils/analysis.ts` isolates validation/normalization. `undecidable_ingredients`, `other_evidence`, and `meta` are optional pending team confirmation. Backend responses with mock metadata show an explicit demo warning. There is no automatic frontend mock fallback. Missing metadata cannot establish which server engine ran.

## Design decisions

Original Figma SVGs are stored in src/assets; the landing illustration is recreated from the editable Figma rectangle layers in CSS. Inter is served locally. Selection cards retain the updated three-column grid, 116px height, 35px icons and centered checkbox. The camera/gallery controls use the provided SVGs.

English is the only current language; the unimplemented KO switch is omitted. The preview contains the selected photo rather than the design's sample label. Results show all nine allergens, actual backend evidence/verdicts, unknown ingredients, warnings and demo status. These dynamic contents extend the page beyond the static 812px example. No fabricated evidence or safety guarantee is displayed. Crustacean Shellfish uses Figma's short visible label, Shellfish, with its complete accessible checkbox name.

## Checks

```powershell
npm.cmd run typecheck
npm.cmd run build
npx.cmd playwright install chromium
# Backend mock server must be running on port 8000 for the integration test
npm.cmd test
```

Playwright checks all nine selections, session persistence, three viewport sizes, uploads/removal, error handling, request locking, optional response fields, multipart privacy and the real FastAPI mock endpoint. Generated screenshots/reports and dependencies are ignored. Physical iOS Safari / Android Chrome camera capture needs device testing. See VERIFICATION.md for results.
