# OpenSesame frontend

React + TypeScript + Vite. Product analysis uses the official final server, as specified in `docs/decisions/0004-final-pipeline.md`.

## Run the product

From the repository root, configure `.env`:

```dotenv
OPENSESAME_OCR=clova
CLOVA_URL=your_clova_url
CLOVA_SECRET=your_clova_secret
OPENSESAME_FINAL_FALLBACK=
```

Then run the server:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.final.app:app --host 127.0.0.1 --port 8001
```

In another terminal:

```powershell
cd frontend
npm.cmd ci
# Only for first-time setup; preserve an existing .env
Copy-Item .env.example .env
npm.cmd run dev
```

On macOS/Linux use `.venv/bin/python`, `npm`, and `cp` instead. Open http://localhost:5173. The default API address is `http://localhost:8001`; `VITE_API_BASE_URL` overrides it. Restart Vite after changing frontend environment variables. Keep OCR and LLM keys only in the root `.env`, never in frontend variables or Git.

## Official requests and data flow

- Photo: `POST /analyze`, multipart field `file`. The server runs CLOVA OCR, extracts the ingredient section, parses nested ingredients and the allergen statement, then runs the final lexicon/rules classifier. Results displays the returned verdicts, evidence, reasons, notes, and original ingredient text.
- Text: choose **Enter ingredient text** on Scan Ingredients. `POST /analyze-text` receives JSON `{ "text": "the ingredient label and allergen statement" }`. The same final parser/classifier runs without OCR. The server also supports `{ "ingredients": "...", "declaration": "..." }` for separate fields.
- `GET /health` reports the configured OCR engine and `final-lexicon-v1`. OCR credentials are initialized on the first photo request, so text analysis can run without OCR keys. Health is a server/configuration check, not proof that an external OCR call succeeded.

The product needs no temporary launcher or LLM credits. `src.app.main` on port 8000 and evaluation scripts remain for comparison experiments; they are not the product backend. Optional `OPENSESAME_FINAL_FALLBACK=llm` enables the existing fallback only for unresolved names.

There is no frontend sample fallback. Responses marked with mock OCR/classification are rejected. Missing OCR configuration returns 503, OCR service failures return 502, and invalid uploads or text return 4xx responses. Previously configured shell environment variables take precedence over `.env`; remove stale mock overrides and restart the server.

## Results and privacy

Confirmed / Likely / Cannot determine come from server verdicts. A missing finding is shown as Not detected only when analysis is complete; otherwise Cannot determine. Not detected does not mean safe. Unknown ingredients and warnings remain visible. Only the U.S. nine major allergens are checked.

Selected allergies stay in browser localStorage (`opensesame.allergies`) and are compared locally. Clear My Information removes the profile. Neither image nor text requests include the profile. Uploaded photos and analysis responses stay in memory. Reloading Results requires another analysis. Object URLs used for previews are released.

## Verification

```powershell
npm.cmd run build
npx.cmd playwright install chromium
# Isolated browser regression tests with controlled server responses
npx.cmd playwright test --grep-invert "real FastAPI mock endpoint"
# Starts the real final server and Vite on isolated ports; no API interception
npm.cmd run test:integration
```

The integration test verifies actual text requests and Results rendering without OCR keys or mock data. For live photo validation, set a real product label path and configure CLOVA credentials first:

```powershell
$env:OPENSESAME_TEST_PHOTO='C:\path\to\product-label.jpg'
npm.cmd run test:integration
```

The live photo test uploads the file to the real server, checks CLOVA metadata and extracted ingredients, and compares rendered evidence with the response. Without a photo path it is explicitly skipped. This verifies data flow, not OCR transcription accuracy or allergen accuracy; compare the original label manually. Do not commit product photos or secrets. Real mobile camera behavior still needs device verification.

The legacy test named `real FastAPI mock endpoint` requires an explicitly started comparison mock server on port 8000 and tests rejection of demo responses. It is separate from product integration.
